# Gripper meshes

These files are copied byte for byte. Do not edit them.

- Source: MuJoCo Menagerie, https://github.com/google-deepmind/mujoco_menagerie
- Folder: `robotstudio_so101/assets/`
- Commit: `822c2d8f877dd166c5b7d3c9f7e3c3b6589473b7`
- License: Apache-2.0 (`LICENSE.mujoco_menagerie`). The upstream CAD comes from
  TheRobotStudio SO-ARM100, also Apache-2.0.

| File | Part | SHA-256 |
|---|---|---|
| `wrist_roll_follower_so101_v1.stl` | fixed jaw (`Wrist_Roll_Follower_SO101`) | `4b17b410a12d64ec39554abc3e8054d8a97384b2dc4a8d95a5ecb2a93670f5f4` |
| `moving_jaw_so101_v1.stl` | moving jaw | `785a9dded2f474bc1d869e0d3dae398a3dcd9c0c345640040472210d2861fa9d` |
| `sts3215_03a_v1.stl` | gripper motor (STS3215) | `a37c871fb502483ab96c256baf457d36f2e97afc9205313d9c5ab275ef941cd0` |

The fixed-jaw mesh matches the official print STL
(`STL/SO101/Individual/Wrist_Roll_Follower_SO101.stl` in SO-ARM100) with a mean
gap of 0.0035 mm and a largest gap of 0.07 mm.
