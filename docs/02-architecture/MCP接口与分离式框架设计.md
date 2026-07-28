# 私有化高中物理题库系统｜MCP 接口与分离式框架设计

文档版本：V1.1  
更新时间：2026-07-26

## 一、设计目标

本设计不仅定义 MCP 工具接口，还定义主程序与 AI 能力之间的分层边界，目标是：

1. 业务层不直接依赖具体模型
2. MCP 工具可替换为本地模型、云端模型或模拟实现
3. 不同开发者可以并行开发不同层
4. 接口文档可直接作为多人协作契约
5. 后续新增工具时不影响现有业务代码

## 二、总体分层

建议采用五层分离式结构：

### 2.1 表现层
负责页面、按钮、表单、预览、任务状态展示。

### 2.2 业务应用层
负责导入任务、录题流程、校对流程、题库流程、组卷流程。

### 2.3 领域服务层
负责稳定的业务能力抽象，例如：
1. 文档解析服务
2. 题目解析服务
3. 知识点生成服务
4. 元数据标注服务

### 2.4 MCP 适配层
负责：
1. 组装 MCP 请求
2. 调用具体工具
3. 清洗响应
4. 统一错误结构
5. 超时、重试、日志

### 2.5 基础设施层
负责：
1. SQLite
2. 文件系统
3. 日志
4. 缓存
5. 配置
6. MCP 进程管理

## 三、推荐目录结构

```text
src/
  app/
    services/
      document_parse_service.ts
      question_analysis_service.ts
      knowledge_service.ts
      metadata_service.ts

  domain/
    models/
      question.ts
      import_batch.ts
      ai_task.ts
    contracts/
      document_parser.ts
      analysis_generator.ts
      knowledge_generator.ts
      metadata_generator.ts

  adapters/
    mcp/
      clients/
        mcp_client.ts
      providers/
        vl_provider.ts
        llm_provider.ts
      tools/
        parse_document_tool.ts
        generate_analysis_tool.ts
        generate_knowledge_tool.ts
        generate_metadata_tool.ts
      schemas/
        parse_document.schema.ts
        generate_analysis.schema.ts
        generate_knowledge.schema.ts
        generate_metadata.schema.ts

  infrastructure/
    db/
    fs/
    cache/
    logging/
    config/
```

## 四、核心设计原则

1. 先定义领域契约，再落具体 MCP 工具
2. 工具名属于适配层，不属于业务层
3. 所有工具必须有输入 DTO 和输出 DTO
4. AI 输出不能直接写数据库

## 五、领域契约设计

### 5.1 文档解析契约

```ts
export interface DocumentParser {
  parseDocument(input: ParseDocumentInput): Promise<ParseDocumentOutput>;
  detectQuestionRegions(input: DetectQuestionRegionsInput): Promise<DetectQuestionRegionsOutput>;
  parseQuestionRegion(input: ParseQuestionRegionInput): Promise<ParseQuestionRegionOutput>;
}
```

### 5.2 试题解析契约

```ts
export interface AnalysisGenerator {
  generateAnalysis(input: GenerateAnalysisInput): Promise<GenerateAnalysisOutput>;
}
```

### 5.3 知识点生成契约

```ts
export interface KnowledgeGenerator {
  generateKnowledge(input: GenerateKnowledgeInput): Promise<GenerateKnowledgeOutput>;
}
```

### 5.4 元数据标注契约

```ts
export interface MetadataGenerator {
  generateMetadata(input: GenerateMetadataInput): Promise<GenerateMetadataOutput>;
}
```

## 六、适配层职责

适配层只做“协议转换”，不做业务决策。

适配层负责：
1. 把领域输入 DTO 转成 MCP 请求 JSON
2. 调用 MCP 工具
3. 处理超时与重试
4. 清洗返回数据
5. 做 Schema 校验
6. 把响应映射回领域 DTO

适配层不负责：
1. 是否入库
2. 是否覆盖人工数据
3. 是否采用 AI 结果
4. 是否合并重复题
5. 是否移动目录

## 七、MCP Client 统一接口

```ts
export interface McpClient {
  call<TReq, TRes>(toolName: string, payload: TReq, options?: McpCallOptions): Promise<TRes>;
}
```

```ts
export interface McpCallOptions {
  timeoutMs?: number;
  retryTimes?: number;
  traceId?: string;
}
```

## 八、工具接口定义方式

每个工具建议固定 4 个文件：

1. `xxx.contract.ts`
2. `xxx.schema.ts`
3. `xxx_tool.ts`
4. `xxx_service.ts`

以 `generate_metadata` 为例：

```text
domain/contracts/metadata_generator.ts
adapters/mcp/schemas/generate_metadata.schema.ts
adapters/mcp/tools/generate_metadata_tool.ts
app/services/metadata_service.ts
```

## 九、标准响应包装

```ts
export interface Result<T> {
  success: boolean;
  data?: T;
  errors?: AppError[];
  warnings?: AppWarning[];
}
```

```ts
export interface AppError {
  code: string;
  message: string;
  target?: string;
  retryable: boolean;
}
```

```ts
export interface AppWarning {
  code: string;
  message: string;
  target?: string;
}
```

## 十、推荐错误码分层

### 10.1 协议层错误
1. `MCP_TIMEOUT`
2. `MCP_PROCESS_EXITED`
3. `MCP_INVALID_RESPONSE`
4. `MCP_TOOL_NOT_FOUND`

### 10.2 数据层错误
1. `INVALID_JSON`
2. `SCHEMA_VALIDATION_FAILED`
3. `MISSING_REQUIRED_FIELD`
4. `ENUM_OUT_OF_RANGE`
5. `QUESTION_ID_MISMATCH`

### 10.3 业务层错误
1. `QUESTION_NOT_FOUND`
2. `IMAGE_REFERENCE_MISSING`
3. `KNOWLEDGE_POINT_INVALID`
4. `MANUAL_DATA_PROTECTED`
5. `BATCH_PARTIAL_FAILED`

## 十一、方便他人应用的关键约束

1. 所有接口都要稳定命名
2. 所有请求都要版本化
3. 所有约束都外置
4. 所有 AI 输出都要可预览
5. 所有工具都要支持 Mock

## 十二、推荐依赖注入方式

```ts
export interface ServiceContainer {
  documentParser: DocumentParser;
  analysisGenerator: AnalysisGenerator;
  knowledgeGenerator: KnowledgeGenerator;
  metadataGenerator: MetadataGenerator;
}
```

业务层只依赖 `ServiceContainer`，不依赖具体实现类。

## 十三、离线模式设计

建议提供 `DisabledMetadataGenerator` 这类空实现：

```ts
class DisabledMetadataGenerator implements MetadataGenerator {
  async generateMetadata(): Promise<GenerateMetadataOutput> {
    throw new AppServiceError("AI_DISABLED", "AI service is disabled");
  }
}
```

## 十四、建议优先落地的 4 个稳定契约

1. `DocumentParser`
2. `AnalysisGenerator`
3. `KnowledgeGenerator`
4. `MetadataGenerator`

## 十五、最终建议

这套系统如果要方便别人应用，不要把“工具接口设计”写成单纯的 JSON 清单，而要写成：

1. 领域契约
2. 适配层协议
3. DTO 模型
4. 错误码规范
5. 可替换实现方式
6. Mock 与离线策略
