# templates.json 字段说明

## 顶层数组

```json
[
  { ... },  // 每个对象代表一个UI元素模板
  { ... }
]
对象字段
字段	类型	示例值	说明
image_file	string	"replace_btn.png"	图片文件名/元素标识符
timestamp	string	"2026-06-16T11:52:32.716661"	数据生成时间
original_size	object	{"width": 900, "height": 1600}	原始图片尺寸
crop_region	object	{"x1": 632, "y1": 1155, "x2": 814, "y2": 1238}	裁剪区域坐标
crop_size	object	{"width": 182, "height": 83}	裁剪后图片尺寸
key_colors	object	{"top_left": {...}, ...}	关键点颜色数据
original_size
字段	类型	示例值	说明
width	int	900	原始图片宽度(px)
height	int	1600	原始图片高度(px)
crop_region
字段	类型	示例值	说明
x1	int	632	左上角X坐标
y1	int	1155	左上角Y坐标
x2	int	814	右下角X坐标
y2	int	1238	右下角Y坐标
crop_size
字段	类型	示例值	说明
width	int	182	裁剪图宽度(px)
height	int	83	裁剪图高度(px)
key_colors
包含5个采样点，每个采样点结构相同：

采样点	说明
top_left	左上角
top_right	右上角
bottom_left	左下角
bottom_right	右下角
center	中心点
每个采样点：

字段	类型	示例值	说明
x	int	0	相对裁剪图的X偏移(px)
y	int	0	相对裁剪图的Y偏移(px)
rgb	array	[160, 144, 124]	RGB颜色值[红,绿,蓝] 0-255
完整示例
json
{
  "image_file": "replace_btn.png",
  "timestamp": "2026-06-16T11:52:32.716661",
  "original_size": {
    "width": 900,
    "height": 1600
  },
  "crop_region": {
    "x1": 632,
    "y1": 1155,
    "x2": 814,
    "y2": 1238
  },
  "crop_size": {
    "width": 182,
    "height": 83
  },
  "key_colors": {
    "top_left": {
      "x": 0,
      "y": 0,
      "rgb": [160, 144, 124]
    },
    "top_right": {
      "x": 181,
      "y": 0,
      "rgb": [160, 144, 122]
    },
    "bottom_left": {
      "x": 0,
      "y": 82,
      "rgb": [160, 144, 123]
    },
    "bottom_right": {
      "x": 181,
      "y": 82,
      "rgb": [158, 142, 120]
    },
    "center": {
      "x": 91,
      "y": 41,
      "rgb": [110, 41, 41]
    }
  }
}