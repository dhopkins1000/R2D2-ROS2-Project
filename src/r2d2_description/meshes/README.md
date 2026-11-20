# R2D2 Mesh-Verzeichnis

Platzhalter für STL/DAE Mesh-Dateien. Die URDF nutzt aktuell Primitive-Shapes
(Cylinder/Box). Mesh-Slots sind in den Xacro-Dateien als auskommentierte
`<mesh>`-Blöcke bereits vorbereitet.

## Erwartete Dateien (bei Bedarf hier ablegen)

| Datei | Verwendet in | Slot |
|-------|--------------|------|
| `chassis.stl` | `urdf/chassis.xacro` | `chassis_link` |
| `wheel.stl` | `urdf/chassis.xacro` | `left_wheel_link`, `right_wheel_link` |
| `leg.stl` | `urdf/chassis.xacro` | `left_leg_link`, `right_leg_link` |
| `dome.stl` | `urdf/dome.xacro` | `dome_link` |
| `xtion.stl` | `urdf/sensors.xacro` | `xtion_link` |

## Umschalten auf Mesh

In der jeweiligen Xacro-Datei den primitiven `<geometry>`-Eintrag durch den
auskommentierten `<mesh>`-Block ersetzen:

```xml
<geometry>
  <!-- <cylinder radius="${chassis_radius}" length="${chassis_height}"/> -->
  <mesh filename="package://r2d2_description/meshes/chassis.stl"/>
</geometry>
```

Nach dem Austausch: `colcon build --packages-select r2d2_description` reicht —
die URDF wird zur Launch-Zeit neu generiert.
