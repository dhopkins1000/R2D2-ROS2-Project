#!/usr/bin/env python3
"""
llm_node.py

Listens on /r2d2/llm_input for text prompts, calls gemini-cli in headless
mode, and publishes the structured JSON response to /r2d2/llm_response.

BACKEND: gemini-cli (google-gemini/gemini-cli)
    - Install: npm install -g @google/gemini-cli
    - Auth:    set GEMINI_API_KEY (and/or GOOGLE_API_KEY) in /etc/r2d2/env
    - GEMINI.md in /home/r2d2/soul is loaded automatically as system context

AUTH NOTE:
    gemini-cli requires GEMINI_API_KEY. If only GOOGLE_API_KEY is set,
    this node copies it to GEMINI_API_KEY automatically in the subprocess
    environment so both variable names work.

NVM / PATH NOTE:
    gemini-cli requires Node.js v18+. This node scans ~/.nvm/versions/node/
    at startup for the highest installed version and prepends it to the
    subprocess PATH automatically. No manual PATH changes needed.

Usage:
    ros2 run r2d2_soul llm_node

Topics:
    Subscribed:  /r2d2/llm_input    std_msgs/String  - prompt text
    Published:   /r2d2/llm_response std_msgs/String  - JSON response dict
                 /r2d2/llm_busy     std_msgs/Bool    - True while processing

ROS2 Parameters:
    soul_workspace   (string)  Path to soul workspace.
                               Default: /home/r2d2/soul
    model            (string)  Gemini model.
                               Default: gemini-2.5-flash
    response_timeout (float)   Seconds before giving up.
                               Default: 60.0
    gemini_path      (string)  Explicit path to gemini binary.
                               Empty = auto-resolve.
                               Default: ''
"""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String


_FENCE_RE = re.compile(r'^```(?:json)?\s*\n?(.*?)\n?```\s*$', re.DOTALL)

_NPM_GLOBAL_DIRS = [
    '/usr/local/bin',
    '/usr/bin',
    os.path.expanduser('~/.npm-global/bin'),
    os.path.expanduser('~/.local/bin'),
]


def strip_fences(text: str) -> str:
    m = _FENCE_RE.match(text.strip())
    return m.group(1).strip() if m else text.strip()


def safe_get(d, *keys, default=None):
    for key in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(key, default)
    return d


def find_nvm_node_bin() -> str | None:
    """Return bin dir of the highest nvm-installed Node.js version."""
    nvm_versions = Path.home() / '.nvm' / 'versions' / 'node'
    if not nvm_versions.is_dir():
        return None
    versions = sorted(
        (d for d in nvm_versions.iterdir() if d.is_dir()),
        key=lambda p: tuple(int(x) for x in p.name.lstrip('v').split('.')
                            if x.isdigit()),
        reverse=True,
    )
    for v in versions:
        bin_dir = v / 'bin'
        if (bin_dir / 'node').is_file():
            return str(bin_dir)
    return None


def build_subprocess_env() -> dict:
    """
    Build subprocess environment:
    - Prepend nvm Node.js bin to PATH
    - Ensure GEMINI_API_KEY is set (copy from GOOGLE_API_KEY if needed)
    """
    env = os.environ.copy()

    # PATH: nvm node first, then common npm global dirs
    extra: list[str] = []
    nvm_bin = find_nvm_node_bin()
    if nvm_bin:
        extra.append(nvm_bin)
    extra.extend(_NPM_GLOBAL_DIRS)
    env['PATH'] = ':'.join(extra) + ':' + env.get('PATH', '')

    # Auth: gemini-cli requires GEMINI_API_KEY specifically.
    # If only GOOGLE_API_KEY is set, copy it over automatically.
    if not env.get('GEMINI_API_KEY') and env.get('GOOGLE_API_KEY'):
        env['GEMINI_API_KEY'] = env['GOOGLE_API_KEY']

    return env


def resolve_gemini(explicit_path: str, env: dict) -> str | None:
    if explicit_path:
        p = Path(explicit_path)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return shutil.which('gemini', path=env.get('PATH', ''))


def get_node_version(env: dict) -> str:
    try:
        node = shutil.which('node', path=env.get('PATH', ''))
        if node:
            r = subprocess.run([node, '--version'], capture_output=True,
                               text=True, timeout=5, env=env)
            return r.stdout.strip()
    except Exception:
        pass
    return 'unknown'


class LlmNode(Node):

    def __init__(self):
        super().__init__('llm_node')

        self.declare_parameter('soul_workspace',   '/home/r2d2/soul')
        self.declare_parameter('model',            'gemini-2.5-flash')
        self.declare_parameter('response_timeout', 60.0)
        self.declare_parameter('gemini_path',      '')

        self._workspace       = Path(self.get_parameter('soul_workspace').get_parameter_value().string_value)
        self._model           = self.get_parameter('model').get_parameter_value().string_value
        self._timeout         = self.get_parameter('response_timeout').get_parameter_value().double_value
        gemini_path_param     = self.get_parameter('gemini_path').get_parameter_value().string_value

        self._env        = build_subprocess_env()
        self._gemini_bin = resolve_gemini(gemini_path_param, self._env)

        self._busy = False
        self._pub_response = self.create_publisher(String, '/r2d2/llm_response', 10)
        self._pub_busy     = self.create_publisher(Bool,   '/r2d2/llm_busy',     10)
        self._sub = self.create_subscription(
            String, '/r2d2/llm_input', self._on_input, 10
        )

        # Startup diagnostics
        nvm_bin  = find_nvm_node_bin()
        api_key  = self._env.get('GEMINI_API_KEY', '')
        key_src  = ('GEMINI_API_KEY' if os.environ.get('GEMINI_API_KEY')
                    else 'GOOGLE_API_KEY (copied)' if api_key else 'NOT SET')

        self.get_logger().info(f'Soul workspace  : {self._workspace}')
        self.get_logger().info(f'Model           : {self._model}')
        self.get_logger().info(f'nvm node bin    : {nvm_bin or "not found"}')
        self.get_logger().info(f'Node.js version : {get_node_version(self._env)}')
        self.get_logger().info(f'gemini binary   : {self._gemini_bin or "NOT FOUND"}')
        self.get_logger().info(f'GEMINI_API_KEY  : {"set" if api_key else "MISSING"} ({key_src})')

        if not self._gemini_bin:
            self.get_logger().error('gemini not found — install: npm install -g @google/gemini-cli')
        if not api_key:
            self.get_logger().error('GEMINI_API_KEY missing — add to /etc/r2d2/env')

        self.get_logger().info('Listening on /r2d2/llm_input - ready.')

    def _on_input(self, msg: String):
        prompt = msg.data.strip()
        if not prompt:
            self.get_logger().warn('Empty prompt - ignoring.')
            return
        if self._busy:
            self.get_logger().warn(f'Busy - dropping: "{prompt[:60]}"')
            return

        self._busy = True
        self._publish_busy(True)
        self.get_logger().info(f'Prompt: "{prompt[:80]}"')

        try:
            result = self._call_gemini(prompt)
            self._log_response(result)
            self._publish_response(result)
        except Exception as e:
            self.get_logger().error(f'Unhandled error: {e}')
            self._publish_response(self._error(str(e)))
        finally:
            self._busy = False
            self._publish_busy(False)

    def _call_gemini(self, prompt: str) -> dict:
        if not self._gemini_bin:
            return self._error('gemini binary not found')

        cmd = [self._gemini_bin, '-p', prompt,
               '--output-format', 'json', '--model', self._model, '--yolo']

        t_start = time.monotonic()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=self._timeout,
                                  cwd=str(self._workspace), env=self._env)
        except subprocess.TimeoutExpired:
            return self._error(f'gemini timed out after {self._timeout}s')
        except FileNotFoundError:
            return self._error(f'gemini binary not executable: {self._gemini_bin}')

        latency = time.monotonic() - t_start

        if proc.returncode != 0:
            stderr = proc.stderr.strip()[:400]
            self.get_logger().error(f'gemini exit {proc.returncode}: {stderr}')
            return self._error(f'gemini exited with code {proc.returncode}: {stderr}')

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            return self._error(f'Envelope JSON parse failed: {e}')

        response_text = envelope.get('response', '')
        clean_text    = strip_fences(response_text)
        if clean_text != response_text:
            self.get_logger().warn('Model used markdown fences - stripped.')

        try:
            structured = json.loads(clean_text)
        except json.JSONDecodeError as e:
            self.get_logger().error(f'Response not valid JSON: {e}')
            return self._error(f'Response JSON parse failed: {e}')

        if not isinstance(structured, dict):
            return self._error(f'Response is {type(structured).__name__}, expected dict')

        stats        = envelope.get('stats', {})
        models_stats = stats.get('models', {}) if isinstance(stats, dict) else {}
        total_cached = sum(m.get('tokens', {}).get('cached', 0)
                           for m in models_stats.values() if isinstance(m, dict))
        total_tokens = sum(m.get('tokens', {}).get('total', 0)
                           for m in models_stats.values() if isinstance(m, dict))

        structured['_meta'] = {
            'latency_s': round(latency, 2), 'cost_usd': 0.0,
            'model': self._model, 'total_tokens': total_tokens,
            'cached_tokens': total_cached, 'error': None,
        }
        return structured

    def _log_response(self, r: dict):
        meta = r.get('_meta', {}) if isinstance(r, dict) else {}
        lcd  = r.get('lcd', {})   if isinstance(r, dict) else {}
        self.get_logger().info('--- LLM Response ---')
        self.get_logger().info(f'  goal         : {r.get("goal") if isinstance(r, dict) else "?"}')
        self.get_logger().info(f'  intent       : {safe_get(r, "utterance", "intent")}')
        self.get_logger().info(f'  intensity    : {safe_get(r, "utterance", "intensity")}')
        self.get_logger().info(f'  lcd line1    : {safe_get(lcd, "line1", default="")}')
        self.get_logger().info(f'  lcd line2    : {safe_get(lcd, "line2", default="")}')
        self.get_logger().info(f'  mood_delta   : {r.get("mood_delta") if isinstance(r, dict) else "?"}')
        self.get_logger().info(f'  memory       : {r.get("memory_write") if isinstance(r, dict) else "?"}')
        self.get_logger().info(f'  latency      : {meta.get("latency_s")}s')
        self.get_logger().info(f'  total_tokens : {meta.get("total_tokens")}')
        self.get_logger().info(f'  cached_tokens: {meta.get("cached_tokens")}')
        if meta.get('error'):
            self.get_logger().error(f'  error        : {meta["error"]}')

    def _publish_response(self, response: dict):
        msg = String()
        msg.data = json.dumps(response)
        self._pub_response.publish(msg)

    def _publish_busy(self, busy: bool):
        msg = Bool()
        msg.data = busy
        self._pub_busy.publish(msg)

    def _error(self, msg: str) -> dict:
        self.get_logger().error(f'LLM error: {msg}')
        return {
            'goal': 'idle', 'goal_params': {},
            'utterance': {'intent': 'alert_warning', 'intensity': 0.8},
            'lcd': {'line1': 'LLM Fehler', 'line2': 'Siehe Log'},
            'mood_delta': {'curiosity': 0.0, 'boredom': 0.0, 'social': 0.0},
            'memory_write': None, 'internal_note': msg,
            '_meta': {'latency_s': 0.0, 'cost_usd': 0.0, 'model': self._model,
                      'total_tokens': 0, 'cached_tokens': 0, 'error': msg},
        }


def main(args=None):
    rclpy.init(args=args)
    node = LlmNode()
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
