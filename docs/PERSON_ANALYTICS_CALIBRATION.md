# 地面坐标标定

第一版默认 `coordinate_mode=image`。要启用地面坐标，配置至少四组对应点：

```yaml
image_points: [[100,200], [800,200], [800,700], [100,700]]
world_points: [[0,0], [4,0], [4,3], [0,3]]
```

只有完成相机标定并检查重投影误差后，才可以将 bbox bottom-center 转换为 `x_world/y_world`；当前系统不修改 Foxglove 的 camera/lidar TF。

