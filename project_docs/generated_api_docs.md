# Knowledge Transformer Engine 接口文档

- 版本：`v1`
- 基础路径：`/api/v1`
- 生成时间：2025-12-05 03:10:31Z

## 认证
所有 `/api/v1` 业务接口默认需要在请求头携带 `X-Appid` 与 `X-Key`。
可通过 `python scripts/manage_appkey.py generate` 创建凭证，或使用查询参数 `appid`/`key` 传递。

## 接口列表

### POST `/api/v1/convert`

**概述**：Submit Conversion

**请求体（application/json）**
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `task_name` | `string` | ✓ | Human-readable task identifier |
| `files` | `array[schema:ConversionFile]` | ✓ |  |
| `priority` | `string` |  |  |
| `callback_url` | `object` |  | Optional webhook notified after conversion |

**响应**
- **202** Successful Response
    **返回体（application/json）**
    | 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `status` | `string` | ✓ |  |
| `task_id` | `object` |  |  |
| `message` | `object` |  |  |
| `error_code` | `object` |  |  |
| `error_status` | `object` |  |  |

- **422** Validation Error
    **返回体（application/json）**
    | 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `detail` | `array[schema:ValidationError]` |  |  |


### GET `/api/v1/formats`

**概述**：List Formats

**响应**
- **200** Successful Response
    **返回体（application/json）**
    | 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `formats` | `array[schema:FormatDescriptor]` | ✓ |  |


### GET `/api/v1/monitor/health`

**概述**：Health Check

**响应**
- **200** Successful Response
    **返回体（application/json）**
    | 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `status` | `string` |  |  |
| `timestamp` | `string` | ✓ |  |
| `dependencies` | `object` |  |  |


### GET `/healthz`

**概述**：Root Health

**响应**
- **200** Successful Response
    **返回体（application/json）**
    ```json
    {
  "additionalProperties": {
    "type": "string"
  },
  "type": "object",
  "title": "Response Root Health Healthz Get"
}
    ```


## 数据模型

### ConversionFile
**字段**
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `source_format` | `string` | ✓ | Original file format, e.g., doc |
| `target_format` | `string` | ✓ | Desired output format, e.g., docx |
| `input_url` | `object` |  | Optional URL to fetch input |
| `object_key` | `object` |  | Storage object key reference |
| `size_mb` | `number` | ✓ | Reported file size in megabytes |

### ConversionRequest
**字段**
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `task_name` | `string` | ✓ | Human-readable task identifier |
| `files` | `array[schema:ConversionFile]` | ✓ |  |
| `priority` | `string` |  |  |
| `callback_url` | `object` |  | Optional webhook notified after conversion |

### ConversionResponse
**字段**
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `status` | `string` | ✓ |  |
| `task_id` | `object` |  |  |
| `message` | `object` |  |  |
| `error_code` | `object` |  |  |
| `error_status` | `object` |  |  |

### FormatDescriptor
**字段**
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `source` | `string` | ✓ |  |
| `target` | `string` | ✓ |  |
| `plugin` | `object` |  |  |

### FormatsResponse
**字段**
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `formats` | `array[schema:FormatDescriptor]` | ✓ |  |

### HTTPValidationError
**字段**
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `detail` | `array[schema:ValidationError]` |  |  |

### HealthResponse
**字段**
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `status` | `string` |  |  |
| `timestamp` | `string` | ✓ |  |
| `dependencies` | `object` |  |  |

### ValidationError
**字段**
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `loc` | `array[object]` | ✓ |  |
| `msg` | `string` | ✓ |  |
| `type` | `string` | ✓ |  |
