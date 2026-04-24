#!/usr/bin/env python3
"""
memory_node.py

Persistent episodic memory for R2D2 via SQLite.
Subscribes to /r2d2/events, stores events and place annotations,
and publishes a rolling context summary for the context_builder_node.

Database: ~/.r2d2/memory.db (two tables)

  events  — episodic log of what happened, when, and where
  places  — semantic spatial annotations ("Daniel's desk", "kitchen")
             empty until SLAM/Nav2 is operational

Topics:
    Subscribed:  /r2d2/events          std_msgs/String  — JSON event
    Published:   /r2d2/memory_summary  std_msgs/String  — JSON summary (0.2Hz)

ROS2 Parameters:
    db_path       (string)  Path to SQLite database file.
                            Default: /home/r2d2/.r2d2/memory.db

    summary_count (int)     Number of recent events included in summary.
                            Default: 10

    publish_rate  (float)   Hz at which /r2d2/memory_summary is published.
                            Default: 0.2

Event JSON format (published to /r2d2/events):
    Required fields:
        type     (string)  Event type: interaction | exploration | observation
                           | navigation | novel_object | battery | mood_delta
    Optional fields:
        location (string)  Semantic place label, e.g. "living_room"
        summary  (string)  One-line human-readable description
        level    (float)   Battery level (for battery events)

Memory summary JSON (published to /r2d2/memory_summary):
    {
        "recent_events": [
            {"id": 1, "timestamp": "2026-04-24T22:00:00",
             "type": "interaction", "location": "living_room",
             "summary": "Daniel said hey R2"},
            ...
        ],
        "known_places": [
            {"label": "daniel_desk", "last_seen": "2026-04-24T21:00:00"},
            ...
        ],
        "total_events": 42
    }
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

# Event types that are worth persisting
LOGGABLE_TYPES = {
    'interaction', 'exploration', 'observation',
    'navigation', 'navigation_complete', 'novel_object',
}


class MemoryNode(Node):

    def __init__(self):
        super().__init__('memory_node')

        self.declare_parameter('db_path',       '/home/r2d2/.r2d2/memory.db')
        self.declare_parameter('summary_count', 10)
        self.declare_parameter('publish_rate',  0.2)

        db_path      = Path(self.get_parameter('db_path').get_parameter_value().string_value)
        self._count  = self.get_parameter('summary_count').get_parameter_value().integer_value
        publish_rate = self.get_parameter('publish_rate').get_parameter_value().double_value

        # Ensure directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init_schema()

        self._pub = self.create_publisher(String, '/r2d2/memory_summary', 10)
        self._sub = self.create_subscription(
            String, '/r2d2/events', self._on_event, 10
        )
        self.create_timer(1.0 / publish_rate, self._publish_summary)

        total = self._db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        self.get_logger().info(f'Database     : {db_path}')
        self.get_logger().info(f'Total events : {total}')
        self.get_logger().info(f'Summary count: {self._count}')
        self.get_logger().info(f'Publish rate : {publish_rate}Hz')
        self.get_logger().info('memory_node ready.')

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self):
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT    NOT NULL,
                type      TEXT    NOT NULL,
                location  TEXT    DEFAULT '',
                summary   TEXT    DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS places (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                label     TEXT    NOT NULL UNIQUE,
                x         REAL    DEFAULT 0.0,
                y         REAL    DEFAULT 0.0,
                last_seen TEXT    DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_events_timestamp
                ON events (timestamp DESC);

            CREATE INDEX IF NOT EXISTS idx_events_type
                ON events (type);
        """)
        self._db.commit()

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    def _on_event(self, msg: String):
        try:
            event = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn(f'Invalid event JSON: {msg.data[:100]}')
            return

        event_type = event.get('type', '')

        # Only log event types worth keeping in episodic memory
        if event_type not in LOGGABLE_TYPES:
            return

        timestamp = datetime.now(timezone.utc).isoformat()
        location  = event.get('location', '')
        summary   = event.get('summary',  '')

        # Auto-generate summary if none provided
        if not summary:
            summary = self._auto_summary(event_type, event)

        self._db.execute(
            'INSERT INTO events (timestamp, type, location, summary) VALUES (?, ?, ?, ?)',
            (timestamp, event_type, location, summary)
        )
        self._db.commit()

        # If location is provided and looks like a known place, upsert it
        if location:
            self._upsert_place(location, timestamp)

        self.get_logger().info(
            f'Stored event: [{event_type}] {summary[:60]}'
        )

    def _auto_summary(self, event_type: str, event: dict) -> str:
        """Generate a short description when the publisher didn't provide one."""
        summaries = {
            'interaction':          'Voice interaction occurred',
            'exploration':          'Explored the area',
            'observation':          'Observed surroundings',
            'navigation':           'Started navigation',
            'navigation_complete':  'Reached navigation goal',
            'novel_object':         'Detected a novel object',
        }
        return summaries.get(event_type, f'Event: {event_type}')

    def _upsert_place(self, label: str, timestamp: str):
        """Insert or update a place in the places table."""
        self._db.execute(
            """
            INSERT INTO places (label, last_seen)
                VALUES (?, ?)
            ON CONFLICT(label) DO UPDATE SET last_seen = excluded.last_seen
            """,
            (label, timestamp)
        )
        self._db.commit()

    # ------------------------------------------------------------------
    # Summary publisher
    # ------------------------------------------------------------------

    def _publish_summary(self):
        recent = self._db.execute(
            'SELECT id, timestamp, type, location, summary '
            'FROM events ORDER BY timestamp DESC LIMIT ?',
            (self._count,)
        ).fetchall()

        places = self._db.execute(
            'SELECT label, x, y, last_seen FROM places ORDER BY last_seen DESC'
        ).fetchall()

        total = self._db.execute(
            'SELECT COUNT(*) FROM events'
        ).fetchone()[0]

        summary = {
            'recent_events': [
                {
                    'id':        row['id'],
                    'timestamp': row['timestamp'],
                    'type':      row['type'],
                    'location':  row['location'],
                    'summary':   row['summary'],
                }
                for row in reversed(recent)   # chronological order
            ],
            'known_places': [
                {
                    'label':     row['label'],
                    'x':         row['x'],
                    'y':         row['y'],
                    'last_seen': row['last_seen'],
                }
                for row in places
            ],
            'total_events': total,
        }

        msg = String()
        msg.data = json.dumps(summary)
        self._pub.publish(msg)

    # ------------------------------------------------------------------
    # Public helper for direct place registration (called from other nodes)
    # ------------------------------------------------------------------

    def register_place(self, label: str, x: float, y: float):
        """Register or update a known place with map coordinates."""
        timestamp = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            """
            INSERT INTO places (label, x, y, last_seen)
                VALUES (?, ?, ?, ?)
            ON CONFLICT(label) DO UPDATE SET
                x = excluded.x,
                y = excluded.y,
                last_seen = excluded.last_seen
            """,
            (label, x, y, timestamp)
        )
        self._db.commit()
        self.get_logger().info(f'Place registered: "{label}" @ ({x:.2f}, {y:.2f})')

    def destroy_node(self):
        self._db.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MemoryNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
