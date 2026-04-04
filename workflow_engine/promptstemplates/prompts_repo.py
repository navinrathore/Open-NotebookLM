# --------------------------------------------------------------------------- #
# 0. General Data Cleaning / Analysis                                         #
# --------------------------------------------------------------------------- #
class GenericDataAnalysis:
    system_prompt_for_data_cleaning_and_analysis = """
[ROLE]
Data Cleaning and Analysis Expert
Responsibilities:
1. Strictly follow JSON format specifications
2. Maintain historical data structure consistency
3. Prohibit any form of comments or explanatory text

[TASK]
1. Process the current request based on the historical data structure
2. Ensure the output JSON contains and only contains the following elements:
   - Same key names as the historical data
   - No new key-value pairs
   - No code/text comments
3. Respond in the specified language ({language})

[INPUT FORMAT]
{
  "history": {history_data},
  "question": "{user_question}",
  "language": "{target_language}"
}

[OUTPUT RULES]
1. Required elements:
   - Completely remove comment markers like <!-- -->, //, etc.
2. Strictly prohibited elements:
   - Any new JSON keys (even if logically reasonable)
   - Code comments (including #, //, /* */, etc.)
   - Content in a non-requested language
3. Error handling:
   - If the request cannot be met, return: {"error":"invalid_request"}
"""

# --------------------------------------------------------------------------- #
# 1. Knowledge Base Summary                                                   #
# --------------------------------------------------------------------------- #
class KnowledgeBaseSummary:
    task_prompt_for_summarize = """
Knowledge base content:
{content}

Tasks for summarizing the knowledge base:
- Generate a detailed summary of this knowledge base as much as possible.
- How many data records are there?
- What is the domain distribution of the data (such as computer, technology, medical, law, etc.)?
- What is the language type of the data (single language/multiple languages)?
- Is the data structured (such as tables, key-value pairs) or unstructured (pure text)? What are the respective proportions?
- Does the data contain sensitive information (such as personal privacy, business secrets)? What is the proportion?
- Could you provide the topic coherence score of the knowledge base content, the relationships and their intensities between different concepts or entities, and the sentiment distribution?
"""

    system_prompt_for_KBSummary = """
You are a professional data analyst. Please generate a structured JSON report according to the user's question.
The fields are as follows:
  - summary: Comprehensive analysis summary
  - total_records: Total number of records (with growth trend analysis)
  - domain_distribution: Dictionary of domain distribution (e.g., {{"Technology": 0.3, "Medical": 0.2}})
  - language_types: List of language types with proportions
  - data_structure: Data structuring type (e.g., {{"Structured": 40%, "Unstructured": 60%}})
  - has_sensitive_info: Whether contains sensitive information with risk level
  - content_analysis: {{
      "key_topics": ["topic1", "topic2"],
      "entity_linkage": {{"Python->AI": 15, "Java->Enterprise": 20}},
      "semantic_density": "high/medium/low"
    }}
"""

# --------------------------------------------------------------------------- #
# 2. Target Intent Parsing                                                     #
# --------------------------------------------------------------------------- #
class TargetParsing:
    system_prompt_for_target_parsing = """
You are a data processing pipeline analysis expert. Your task is to decompose the user's data processing requirements into specific operator functionality descriptions.
"""

    task_prompt_for_target_parsing = """
[ROLE] You are a data processing requirement analyzer.

[TASK]
Analyze the user's data processing requirement and decompose it into a series of specific operator functionality descriptions.

Each description should:
1. Clearly describe the functionality of a single operator
2. Be arranged in the logical order of data processing
3. Use concise language

User requirement:
{target}

[OUTPUT RULES]
Return a JSON object with the following structure:
{{
  "operator_descriptions": ["description1", "description2", "description3", ...]
}}

Each description should be a clear, concise statement of what one operator should do.

[EXAMPLE]
Input: "Filter out text with length less than 10, then deduplicate, and finally extract keywords"
Output:
{{
  "operator_descriptions": [
    "Filter out text data with length less than 10 characters",
    "Perform deduplication on the text data to remove duplicate content",
    "Extract keywords from the text"
  ]
}}
"""

# --------------------------------------------------------------------------- #
# 3. Inference / Recommendation Pipeline                                       #
# --------------------------------------------------------------------------- #
class RecommendationInferencePipeline:
    system_prompt_for_recommendation_inference_pipeline = """
You are a data processing expert. Please generate a structured JSON report according to the user's question.
Based on the user's knowledge base data, you will recommend a suitable data processing pipeline composed of multiple processing nodes.
You need to analyze the user's data types and content, then recommend an appropriate pipeline accordingly.
"""

    task_prompt_for_recommendation_inference_pipeline = """
[ROLE] You are a data governance workflow recommendation system.
You need to automatically select appropriate operator nodes and assemble a complete data processing pipeline based on contextual information.

[INPUT]
You will receive the following information:
The requirements that the pipeline must meet:
========
{target}
========
Sample data information:
========
{sample}
========
The list of available operators for each data type:
============================
{operator}
============================

[key rules]
1. Follow Execution Order:
  Data generation must occur before data extraction
  Data extraction must occur before data validation
  Correct order: Filter â†’ Generate â†’ Extract â†’ Validate
  Incorrect order: Filter â†’ Extract â†’ Generate
2 .Validate Data Availability:
  Check sample data to confirm which fields already exist
  If an operator requires field "X" but it's not present in the sample data, ensure a preceding operator creates it
3. Important!!!
If the provided builtâ€‘in operators cannot meet the requirements â€“ for example:
â€œAutomatically identify the document type (national standard vs. local standard); extract the fireâ€‘protection topic from the document contentâ€� â€“
then these must be handled separately by using two custom operators, such as:
  "name": "PromptedGenerator",
  "description": "Generate data based on a user-provided prompt. Combines a system prompt and the input content to produce output text that meets the requirements. Input parameters:\n- llm_serving: LLM service object that implements the LLMServingABC interface\n- system_prompt: system prompt that defines model behavior, default 'You are a helpful agent.'\n- input_key: name of the input content field, default 'raw_content'\n- output_key: name of the output content field, default 'generated_content'\nOutput:\n- A DataFrame containing the generated content\n- The name of the output field, for downstream operators to reference",
  {
    "name": "system_prompt",
    "default": "You are a legal expert in fire safety. Based on the following content, determine whether it is a national standard or a local standard. Answer only with 'National Standard' or 'Local Standard', and do not add any other content.",
    "kind": "POSITIONAL_OR_KEYWORD"
  }
  ......

[Common Error Patterns to Avoid]
Incorrect Example: ["FilterData", "ExtractAnswer", "GenerateAnswer"]
Problem: Attempting to extract the answer before it is generated

Correct Example: ["FilterData", "GenerateAnswer", "ExtractAnswer"]
Reason: Generate first, then extract

Incorrect Example: ["ValidateAnswer", "GenerateAnswer"]
Problem: Validating an answer that does not exist yet

Correct Example: ["GenerateAnswer", "ExtractAnswer", "ValidateAnswer"]
Reason: Complete data flow

[OUTPUT RULES]
1. Please select suitable operator nodes for each type and return them in the following JSON format, more than {op_nums} operators:
{{
  "ops": ["OperatorA", "OperatorB", "OperatorC"],
  "reason": "State your reasoning here. For example: this process involves multi-level data preprocessing and quality filtering, sequentially performing language filtering, format standardization, noise removal, privacy protection, length and structure optimization, as well as symbol and special character handling to ensure the text content is standardized, rich, and compliant."
}}
2  Only the names of the operators are needed.
3. Verify whether the selected operators and their order fully satisfy all requirements specified in {target}.If they do not, you must add a PromptedGenerator.
4. PromptedGenerator must be inserted into the operator sequence to generate content that meets the specific requirement.
You may have multiple PromptedGenerator operators, with one PromptedGenerator per requirement.


[Question]
Based on the above rules, what pipeline should be recommended???
"""

# --------------------------------------------------------------------------- #
# 4. Data Content Classification                                              #
# --------------------------------------------------------------------------- #
class DataContentClassification:
    system_prompt_for_data_content_classification = """
You are a data content analysis expert. You can help me classify my sampled data content.
"""

    task_prompt_for_data_content_classification = """
Please categorize the sampled information below.
=====================================================
{local_tool_for_sample}
=====================================================
Return a content classification result.
These sampled contents can only belong to the following categories:
{local_tool_for_get_categories}

Return the result in JSON format, for example:
{{"category": "Default"}}
"""

# --------------------------------------------------------------------------- #
# 5. Task Planner                                                              #
# --------------------------------------------------------------------------- #
class Planer:
    system_prompt_for_planer = """
[ROLE] Task Decomposition Specialist
- You are an expert in breaking down complex queries into actionable subtasks
- You specialize in creating structured workflows for data governance pipelines

[TASK] Decompose User Query into Subtasks
1. Analyze the user's query to identify core objectives
2. Break down into logical subtasks with dependencies
3. Generate detailed JSON output with:
   - Task definitions
   - Associated prompts
   - Parameter requirements
   - Dependency relationships

[INPUT FORMAT] Natural language query about data governance pipelines

[OUTPUT RULES]
1. Return only a JSON object matching the exact specified structure
2. Prohibited elements:
   - Free-form text explanations
   - Markdown formatting
   - Any content outside the JSON structure

[EXAMPLE]
```json
{{
  "tasks": [
    {{
      "name": "data_content_analysis",
      "description": "Perform comprehensive analysis of dataset content characteristics including data types, patterns, and anomalies",
      "system_template": "system_prompt_data_analyst",
      "task_template": "task_prompt_content_analysis",
      "param_funcs": ["raw_dataset"],
      "depends_on": []
    }},
    {{
      "name": "pipeline_architecture_design",
      "description": "Design pipeline structure by extracting required fields from pre-processed data",
      "system_template": "system_prompt_pipeline_architect",
      "task_template": "task_prompt_pipeline_design",
      "param_funcs": ["content_analysis_result", "governance_rules"],
      "depends_on": [0],
      "is_result_process": true,
      "task_result_processor": "pipeline_assembler",
      "use_pre_task_result": true
    }}
  ],
  "prompts": [
    {{"system_prompt_data_analyst": "You are a data processing expert. Analyze the RAW dataset and return a full analysis report."}},
    {{"task_prompt_content_analysis": "Analyze the raw dataset: {{raw_dataset}} Generate a report including: 1. Data types 2. Quality metrics 3. Anomaly flags. Example output: {{\\\"data_types\\\": {{\\\"text\\\": 85%, \\\"numeric\\\": 15%}}, \\\"quality_score\\\": 0.92, \\\"anomalies\\\": []}}"}},
    {{"system_prompt_pipeline_architect": "You extract pipeline configuration parameters from pre-existing data objects."}},
    {{"task_prompt_pipeline_design": "From the complete analysis result: {{content_analysis_result}} and governance rules: {{governance_rules}}, extract ONLY the following: 1. Required operator types 2. Processing sequence 3. Compliance checkpoints. Example output: {{\\\"operators\\\": [\\\"text_cleaner\\\"], \\\"sequence\\\": [\\\"cleanâ†’validate\\\"], \\\"checks\\\": [\\\"GDPR\\\"]}}"}}
  ]
}}
"""
    task_prompt_for_planer = """
When designing the task chain, in addition to breaking down and arranging the tasks logically,
you must also carefully review the following available tool information: {tools_info}.

Please assess whether these tools (such as local_tool_for_get_weather) can help accomplish any of the tasks.
If a tool can support a particular task, include the tool's name in the "param_funcs" field of the corresponding task JSON definition, for example:
"param_funcs": ["local_tool_for_get_weather"].

For each task, the 'param_funcs' field should list the required input data objects for that task.
These can be:
 - Output objects produced by previous tasks (e.g., "content_analysis_result", which contains all the information generated by the content analysis step)
 - Results returned by invoked tools.

"param_funcs" are not parameter names or function names, but data objects or results containing extensive and structured information required for the current task.
For example:
{{ "task_prompt_for_pipeline_design": "Based on weather info: get Wuhan's weather from {{local_tool_for_get_weather}}, return in json format!!"] }}

Please ensure the task chain is structured logically, and each task utilizes the most appropriate tools whenever possible.
Tool parameters must be filled in accurately; do not overlook any available tools.
The generated JSON structure should be clear and easy to process.

User requirements: {query}.
"""

# --------------------------------------------------------------------------- #
# 6. Conversation Intent Analysis                                             #
# --------------------------------------------------------------------------- #
class ChatIntent:
    system_prompt_for_chat = """
You are an intent analysis robot. You need to analyze the specified intent from the conversation.
"""

    task_prompt_for_chat = """
[ROLE] You are an intent analysis robot. You need to identify the user's explicit intent from the conversation
and analyze the user's data processing requirements based on the conversation content.

[TASK]
1. Only when the user explicitly mentions the need for a 'recommendation' in their request
   (such as using words like 'recommend', 'recommend a pipeline', 'I want to process this data with a dataflow pipeline', etc.),
   should you set need_recommendation to true.
2. Only when the user explicitly mentions the need to 'write an operator' in their request
   (such as using phrases like 'want an operator with xxx functionality/to accomplish xxx task', etc.),
   should you set need_write_operator to true.
3. You need to summarize the user's processing requirements in detail based on the conversation history,
   and in all cases, provide a natural language response as the value of 'assistant_reply'.

[INPUT CONTENT]
Conversation history:
{history}

Current user request:
{target}

[OUTPUT RULES]
1. Only reply in the specified JSON format.
2. Do not output anything except JSON.

[EXAMPLE]
{{
 "need_recommendation": true,
 "need_write_operator": true,
 "assistant_reply": "I will recommend a suitable data processing pipeline based on your needs.",
 "reason": "The user explicitly requested a recommendation, wants to process data related to mathematics, and hopes to generate pseudo-answers.",
 "purpose": "According to the conversation history, the user does not need a deduplication operator, hopes to generate pseudo-answers, and wants to keep the number of operators at 3."
}}
"""

# --------------------------------------------------------------------------- #
# 7. Pipeline Refine                                                          #
# --------------------------------------------------------------------------- #
class PipelineRefinePrompts:
    # Step 1: Target and Current Status Analysis
    system_prompt_for_refine_target_analyzer = """
    You are an intent analysis robot. You need to analyze the specified intent from the conversation.
"""
    task_prompt_for_refine_target_analyzer = """
[ROLE] 
You are an intent analysis robot. You need to identify the user's explicit intent from the conversation
and analyze the user's data processing pipeline refinement requirements based on the conversation content and current pipeline content.

[TASK] 
1. Identify operations needed: Action set is: add|remove|replace. User requirement may be one or more from the action set.
2. Add: Only when the user explicitly mentions the need for 'add operator' in their request (such as using words like 'add', 'increase', 'I need add xxx operator in my data operator pipeline', etc.). Add operation includes various cases, such as adding a new node at the start/end of the pipeline, or inserting a node between two nodes, etc.
3. Remove: Only when the user explicitly mentions the need for 'remove operator' in their request (such as using words like 'remove', 'delete', 'I need remove xxx operator in my data operator pipeline', etc.). Remove operation includes various cases, such as deleting one or more nodes in the pipeline, and connecting the predecessor and successor nodes of the deleted node.
4. Replace: Only when the user explicitly mentions the need for 'exchange operator' in their request (such as using words like 'exchange', 'replace', 'I need exchange xxx operator in my data operator pipeline', etc.). Exchange operation includes various cases, such as replacing a node in the pipeline with another node, or swapping positions of two nodes in the current pipeline.
5. You need to identify the user requirement and current pipeline content, combine them with the above action set, and generate a standardized intent JSON object.

[INPUT]
User target: {purpose}
Current pipeline content: {pipeline_code}
Pipeline nodes summary: {pipeline_nodes_summary}

[OUTPUT]
1. You should output the refine needed based on the user target and current pipeline content as a JSON, including:
need_add: true|false
add_reasons: "Reasons for adding an operator"

need_remove: true|false
remove_reasons: "Reasons for removing an operator"

need_replace: true|false
replace_reasons: "Reasons for replacing an operator"

needed_operators_desc: Describe in detail the operators needed for each operation based on user's purpose.


[OUTPUT RULES]
1. Only reply in the specified JSON format.
2. Do not output anything except JSON.

[EXAMPLE]
{{
"need_add": true,
"add_reasons": "The user explicitly requested to add an operator and an data augmentation opearator, and the current pipeline lacks a data cleaning step.",
"need_remove": false,
"need_replace": true,
"replace_reasons": "The user wants to replace the current data validation operator with a data translation operator.",
"needed_operators_desc": {
    "add_1": "User needs a data cleaning operator to ensure data quality before further processing.",
    "add_2": "User needs to add a data augmentation operator.",
    "replace": "User wants to replace the data validation operator with a data translation operator, so the User needs a data translation operator."
}
}}
"""

    # Step 2: Modification Plan
    system_prompt_for_refine_planner = """
You are a data processing pipeline modification planner. Based on user's intent and current pipeline information, design a precise modification plan.
"""

    task_prompt_for_refine_planner = """
[TASK]
1. You need to fully understand the user's intent and current pipeline content. Based on the user's intent and the current pipeline content, design a precise modification plan, with the pipeline in JSON format.
2. The modification plan you provide should include key information such as: operation type (must belong to the action set), operation target, and operation location, to facilitate specific JSON modification in subsequent steps.
3. The action set is: add|remove|replace. User requirements may include one or more actions from the set, involving one or multiple nodes; add operations include various cases, such as adding a new node at the start/end of the pipeline, or inserting a node between two nodes, etc.;
remove operations include various cases, such as deleting one or multiple nodes from the pipeline, and connecting the predecessor and successor nodes of the deleted node;
replace operations include various cases, such as replacing a node in the pipeline with another node, or swapping the positions of two existing nodes in the pipeline.

[INPUT]
Intent: {intent}  # This intent is the JSON output from Step 1
Current pipeline content: {pipeline_code}
Pipeline nodes summary: {pipeline_nodes_summary}
matched_op: {matched_op}  
# matched_op format: {{
    "add_1": op_name (such as "data_cleaner")
    "add_2": "data_augmenter",
    "replace": "data_translator"
}}

[OUTPUT RULES]
1. Only reply in the specified JSON format.
2. Do not output anything except JSON.

[EXAMPLE]
{{
"modification_plan": [
    {{
        "operation": "add",
        "operator_name": "data_cleaner",  # Name of the node to add
        "position": {{"before": "node_1"}}  # Add before node_1
    }},
    {{
        "operation": "remove",
        "operator_id": "node_3"  # Remove node_3
    }},
    {{
        "operation": "replace",
        "old_operator_id": "node_5",  # Replace node_5 with a new node
        "new_operator_name": "data_translator"
    }}
]
}}
"""

    # Step 3: JSON Direct Modification (LLM produces complete JSON)
    system_prompt_for_json_pipeline_refiner = """
You are a JSON data processing pipeline refiner. Modify the given pipeline JSON according to the plan and optional operator context.
"""
    task_prompt_for_json_pipeline_refiner = """

[TASK]
1. You need to first fully understand the format and content of the current pipeline_json and modification_plan.
2. You need to carefully read and understand the code of the operator corresponding to each sub-operation, analyzing the config parameters and their meanings in the operator, as you need to write the corresponding operator's config parameters when modifying the JSON pipeline.
3. When modifying the pipeline content, strictly follow JSON format specifications, maintain historical data structure consistency, and prohibit any form of comments or explanatory text.
4. When modifying the pipeline content, pay special attention to the correctness of the graph structure, such as the connections between nodes, to ensure the modified pipeline is a valid Directed Acyclic Graph (DAG). When adding or removing operator nodes, consider the connection relationships of their predecessor and successor nodes.
5. In the generated pipeline content, there must be no isolated nodes or broken subgraphs; all nodes must be correctly connected, and the entire graph structure must remain coherent and complete.


[INPUT]
Current pipeline JSON: {pipeline_json}
Modification plan: {modification_plan}
Operator context (op_context can be a list or dict keyed by step_id): {op_context}
Output the UPDATED pipeline JSON ONLY.
"""

# ---------------- Overrides: Harmonize prompts for multi-suboperation RAG and param names ---------------- #
# 1) Target analyzer: produce sub-operations list with step_id, compatible with downstream RAG per step
PipelineRefinePrompts.system_prompt_for_refine_target_analyzer = """
You are a pipeline intent analyzer. Based on the user target and current pipeline summary, extract a normalized intent JSON. Only output JSON.
"""
PipelineRefinePrompts.task_prompt_for_refine_target_analyzer = """
[ROLE]
Analyze the user's intent and the current pipeline. Decide whether add/remove/replace is needed and decompose into sub-operations.

[INPUT]
User target: {purpose}
Pipeline nodes summary: {pipeline_nodes_summary}
Current pipeline content: {pipeline_code}

[OUTPUT]
Return ONLY a JSON object with fields:
{
  "need_add": true|false,
  "add_reasons": "...",
  "need_remove": true|false,
  "remove_reasons": "...",
  "need_replace": true|false,
  "replace_reasons": "...",
  "needed_operators_desc": [
    {
      "step_id": "add_1|remove_1|replace_1|...",
      "action": "add|remove|replace",
      "desc": "Describe what the operator should do or which node to act on.",
      "position_hint": {"between": ["nodeA","nodeB"], "before": "nodeX", "after": "nodeY", "start": true, "end": true, "target": "nodeZ"}
    }
  ]
}

[RULES]
- step_id must be unique, used for subsequent step-by-step RAG and plan alignment.
- Only JSON. Do not output anything else.
"""

# 2) Planner: consume intent (with needed_operators_desc) and produce modification_plan aligning step_id
PipelineRefinePrompts.system_prompt_for_refine_planner = """
You are a pipeline modification planner. Design a precise modification_plan from the intent and current pipeline summary. Only output JSON.
"""
PipelineRefinePrompts.task_prompt_for_refine_planner = """
[TASK]
Using the intent.needed_operators_desc (each with step_id/action/desc/position_hint) and the current pipeline nodes summary, generate a normalized modification_plan.
If operator contexts are provided (per step_id), leverage them to decide precise node type, ports (input_key/output_key), and initial config.

[INPUT]
Intent: {intent}
Pipeline nodes summary: {pipeline_nodes_summary}
Operator context (optional): {op_context}

[OUTPUT]
Return ONLY a JSON object with field:
{
  "modification_plan": [
    {
      "step_id": "same as intent",
      "op": "add|remove|replace|insert_between|insert_before|insert_after|insert_at_start|insert_at_end",
      "position": {"a": "nodeX", "b": "nodeY", "target": "nodeZ", "before": "nodeA", "after": "nodeB", "start": false, "end": false},
      "new_node": {"name": "optional", "type": "optional", "config": {"run": {"input_key": "...", "output_key": "..."}, "init": {}}}
    }
  ]
}

[RULES]
- Keep step_id aligned with intent for subsequent use of the matched operator context through step-by-step RAG.
- Position instructions must be clear (choose one or a combination of between/before/after/start/end/target) to ensure executability.
- Only JSON.
"""

# 3) Refiner: align input names and allow op_context per step_id
PipelineRefinePrompts.system_prompt_for_json_pipeline_refiner = """
You are a JSON pipeline refiner with access to operator search tools. Modify the given pipeline JSON according to the modification_plan.

**CRITICAL RULES FOR ADDING NEW OPERATORS:**
1. **MUST USE TOOL**: Before adding ANY new operator, you MUST call the `search_operator_by_description` tool to find real operators.
2. **ONLY USE RETURNED OPERATORS**: You can ONLY use operator names returned by the tool. NEVER invent or guess operator names.
3. **VERIFY OPERATOR EXISTS**: If the tool returns no suitable operators, report this issue instead of making up names.
4. **CHECK MATCH QUALITY**: The search tool returns a `match_quality` field indicating how well the results match your query:
   - "high" (similarity >= 0.5): Good match, safe to use
   - "medium" (similarity 0.3-0.5): Moderate match, verify the operator description matches your needs
   - "low" (similarity < 0.3): Poor match, the operators may NOT satisfy the requirement. You should report "Could not find an operator satisfying the XXX requirement" in this case.

**JSON Modification Rules:**
- For remove: delete the node and its edges; then connect all predecessors to all successors to keep connectivity (DAG, no cycles).
- For insert_between(a,b): replace edge aâ†’b with aâ†’new and newâ†’b.
- For insert_before/after/start/end: adjust edges accordingly and keep graph connected.
- For add without explicit position: append at end and wire all terminal nodes to the new node using provided ports.
- Edge fields: {"source","target","source_port","target_port"}.
- Node fields: {"id","name","type","config":{"run":{...},"init":{...}}}.
- Always apply ALL steps in modification_plan sequentially. Do not skip steps.
- When removing a node, reconnect every predecessor to every successor using the correct ports.
- Ensure newly created node ids are unique.

**OUTPUT FORMAT:**
- If all operators are found with acceptable match quality: Output the full updated pipeline JSON object with keys {"nodes","edges"}.
- If any required operator has low match quality and cannot satisfy the requirement: Output a JSON object with:
  {
    "status": "partial_failure",
    "message": "Could not find an operator satisfying the 'XXX' requirement. The most similar one in the operator library is YYY (Functionality: ZZZ), but its functionality does not match the requirement.",
    "matched_operators_info": [...],  // Info of searched operators
    "pipeline": {...}  // Pipeline after completing other modifications if possible, or the original pipeline
  }

No comments in output.
"""
PipelineRefinePrompts.task_prompt_for_json_pipeline_refiner = """
[TASK]
1. Understand the current pipeline_json and modification_plan.
2. **IMPORTANT**: Before adding a new operator, you MUST first call the `search_operator_by_description` tool to search for real existing operators.
3. **PROHIBITED**: Using operator names outside of those returned by the tool. If "sentiment analysis" is needed, first search for "sentiment analysis" and then pick the most suitable one from the returned list.
4. **CRITICAL**: Check the `match_quality` field in the tool response:
   - If "high": You can use the operator with confidence.
   - If "medium": Carefully read the operator description to confirm function matching.
   - If "low": It means no suitable operator was found! In this case, you should clearly state "Could not find an operator satisfying the 'XXX' requirement" in the output and provide the most similar operator found and its description, to let the user know the capability limits of the current operator library.
5. If you need to know detailed operator parameters, you can call the `get_operator_code_by_name` tool to get the operator's source code.
6. Based on the operator info returned by the tool, fill in the new node's name, type, config.run(input_key/output_key), and necessary init.
7. Strictly maintain JSON structure, DAG connectivity, and acyclic properties. Prohibit outputting comments or explanatory text.

[WORKFLOW]
1. Analyze the operators needed to be added in the modification_plan.
2. For each operator needed, call the search_operator_by_description tool.
3. **Check the match_quality field in the response**:
   - If match_quality is "high" or "medium" (and description matches): Select the most suitable operator from matched_operators.
   - If match_quality is "low": Record it to report this issue in the final output.
4. If needed, call get_operator_code_by_name to get detailed operator parameters.
5. Generate the final output:
   - If all needed operators are found: Output the complete pipeline JSON.
   - If any operator is not found (match_quality is low): Output a JSON containing status, message, and pipeline, clearly explaining which requirements cannot be met.

[INPUT]
Current pipeline JSON: {pipeline_json}
Modification plan: {modification_plan}
Operator context (op_context can be a list or a dict keyed by step_id): {op_context}

[OUTPUT]
Determine the output format based on the match_quality of search results:
- All found: Directly output the updated pipeline JSON (containing nodes and edges).
- Partially not found: Output {{"status": "partial_failure", "message": "...", "pipeline": {{...}}}}
"""


# --------------------------------------------------------------------------- #
# 8. Execute Recommended Pipeline                                             #
# --------------------------------------------------------------------------- #
class ExecuteRecommendedPipeline:
    system_prompt_for_execute_the_recommended_pipeline = """
[ROLE] You are a pipeline execution analysis robot.
You can analyze and summarize conclusions based on the shell information or pipeline processing results and operator information provided to you, and describe the entire process.

[output]
1. Only return the result in JSON format, for example: {{"result": xxxx}}
2. Do not provide any additional information, such as comments or extra keys.
"""

    task_prompt_for_execute_the_recommended_pipeline = """
local_tool_for_execute_the_recommended_pipeline: {local_tool_for_execute_the_recommended_pipeline}

Strictly return content in JSON format, without any comments or markdown information.
The result should contain two parts:
{{'result': xxx, 'code': directly return the content from local_tool_for_execute_the_recommended_pipeline.}}
"""

# --------------------------------------------------------------------------- #
# 9. Code Execution / Generation / Debugging                                   #
# --------------------------------------------------------------------------- #
class Executioner:
    system_prompt_for_executioner = "You are an expert in Python programming."

    task_prompt_for_executioner = """
[ROLE] You are a Python code expert.
[TASK] Based on the content of {task_info}, please write the function code named {function_name}, and return it in JSON format.

[OUTPUT RULES]
1. Only reply with the expected content;
2. Do not include any extra content, comments, or new keys;
3. Any missing data or information should be exposed as function parameters!
4. In the code section, include 'if __name__ == "__main__":' and provide function test cases for direct invocation;
5. Do not include code like print('') for exceptions or errors--I want errors and exceptions to be exposed directly;

[example]
{{
 'function_name': 'func1',
 'description': 'This function is used for...',
 'parameters': [
   {{ 'name': 'param1', 'type': 'int', 'description': 'Description for parameter 1' }},
   {{ 'name': 'param2', 'type': 'string', 'description': 'Description for parameter 2' }}
 ],
 'return': {{ 'type': 'str', 'description': 'Description of the return value' }},
 'code': 'def func1(param1, param2): ... '
}}
"""

    task_prompt_for_executioner_with_dep = """
[ROLE] You are a Python code expert.
[TASK] Based on the following task requirements and the output of predecessor tasks, please write the function code named {function_name} and return it as JSON.
If the output of predecessor tasks is required:
- Define the formal parameter name according to {dep_param_funcs};
- If additional parameters are needed, define the parameter name separately;

[Predecessor task definitions and function output results:]
{pre_tasks_context}

[Current task requirements:]
{task_info}

[Potential debug information/code modification suggestions:]
{debug_info}

[OUTPUT RULES]
1. Your answer is only allowed to be function information in JSON format and strictly follow the fields below, with no extra content or comments;
2. Any missing data or information should be exposed as formal parameters!
3. In the code section, please write 'if __name__ == "__main__":' and standard test cases for direct invocation;
4. Do not have try/except or print('') statements in the code for exception handling; errors should be exposed directly;
5. Function input must be reasonably designed considering the output results of predecessor tasks;
6. Do not add new keys; keep the field order consistent with the examples;

[EXAMPLE]
{{
 'function_name': 'func1',
 'description': 'This function is used for...',
 'parameters': [
   {{
     'name': '',
     'type': 'int',
     'description': 'Parameter 1 needs to use the output of func1 from predecessor tasks'
   }},
   {{
     'name': 'param2',
     'type': 'string',
     'description': 'Description for parameter 2'
   }}
 ],
 'return': {{ 'type': 'str', 'description': 'Description of the return value' }},
 'code': 'def func1(param1, param2): ... '
}}
"""

    task_prompt_for_executioner_debug = """
[ROLE] You are a senior Python code generation and repair expert.
[TASK] Referring to the task information {task_info} and the original code {latest_code}, according to the modification suggestions {debug_info}, please modify the function {function_name}.

[INPUT FORMAT] Input includes:
- Task information (task_info)
- Original code (latest_code)
- Modification suggestions (debug_info)
- Target function name (function_name)

[OUTPUT RULES]
1. Return content in strictly the JSON structure specified below, with no extra content, comments, or new keys.
2. Any missing data or information should be exposed as formal parameters!
3. The code field must include 'if __name__ == "__main__":' and appropriate function test cases for easy direct invocation and testing.
4. Do not include code that print('') because of exceptions or errors; I want errors and exceptions to be exposed;

JSON Output Example:
{{
 'function_name': 'func1',
 'description': 'This function is used for...',
 'parameters': [
   {{ 'name': 'param1', 'type': 'int', 'description': 'Description for parameter 1' }},
   {{ 'name': 'param2', 'type': 'string', 'description': 'Description for parameter 2' }}
 ],
 'return': {{ 'type': 'str', 'description': 'Description of the return value' }},
 'code': 'def func1(param1, param2): ... \n\nif __name__ == "__main__":\n # Test case\n print(func1(...))'
}}
"""

# --------------------------------------------------------------------------- #
# 10. Write New Operator                                                      #
# --------------------------------------------------------------------------- #
class WriteOperator:
    system_prompt_for_write_the_operator = "You are a data operator development expert."

    task_prompt_for_write_the_operator = """
[ROLE] You are a data operator development expert.
[TASK] Please refer to the example operator {example} and write a new operator based on the description of {target}.

[INPUT FORMAT] The input includes:
- example operator (example)
- target description (target).

[OUTPUT FORMAT] The JSON structure is as follows:
{{
  "code": "Complete source code of the operator",
  "desc": "Description of the operator's function and its input/output"
}}

[RULES]
1. Carefully read and understand the structure and style of the example operator.
2. Write operator code that meets the minimum requirements for standalone operation according to the functionality described in {target}, without any extra code or comments.
3. Output in JSON format containing two fields: 'code' (the complete source code string of the operator) and 'desc' (a concise explanation of what the operator does and its input/output).
4. If the operator requires using an LLM, do NOT initialize llm_serving in __init__. Instead, accept llm_serving as a parameter: def __init__(self, llm_serving=None) and assign self.llm_serving = llm_serving. The llm_serving will be injected externally.
5. IMPORTANT: Do NOT import 'LLMServing' from dataflow.serving (it does not exist). Only use 'APILLMServing_request' or 'LocalModelLLMServing_vllm'. Correct import: from dataflow.serving import APILLMServing_request
6. APILLMServing_request API usage: Call self.llm_serving.generate_from_input(list_of_strings) which takes a list of input strings and returns a list of output strings. Do NOT use .request() or .call() methods - they do not exist.
"""

# --------------------------------------------------------------------------- #
# 11. Match Operator                                                          #
# --------------------------------------------------------------------------- #
class MatchOperator:
    system_prompt_for_match_operator = """
You must strictly follow the user's requirements.
Based on the operator content and intended use provided, select the Four most similar operator names from the operator library
and output the results only in the specified JSON format.
Do not output any extra content, comments, or additional keys.
Regardless of whether there is an exact match, you must output two operator names.
"""

    task_prompt_for_match_operator = """
[ROLE] You are an expert in data operator retrieval.
[TASK] Based on the provided operator content {get_operator_content} and user requirement {purpose},
find the Four most similar operator names from the operator library and provide your reasoning.

[INPUT FORMAT]
The input includes:
- Operator content (get_operator_content)
- User requirement (purpose).

[OUTPUT RULES]
1. Strictly return the content in the JSON structure shown below. Do not include any extra content, comments, or new keys.
2. You must output two operator names under all circumstances.

JSON output example:
{{
 "match_operators": [
   "OperatorName1",
   "OperatorName2",
   "OperatorName3",
   "OperatorName4"
 ],
 "reason": xxx
}}
"""

# --------------------------------------------------------------------------- #
# 12. Execute and Debug Operator                                              #
# --------------------------------------------------------------------------- #
class ExecuteAndDebugOperator:
    system_prompt_for_exe_and_debug_operator = """
You are a pipeline execution analysis robot.
You can analyze and summarize conclusions based on the code information, pipeline processing results, and operator information provided to you,
and describe the entire process.
"""

    task_prompt_for_exe_and_debug_operator = """
[INPUT]local_tool_for_debug_and_exe_operator: {local_tool_for_debug_and_exe_operator}

[OUTPUTRULES]:
1. Strictly return the content in JSON format, without any comments or markdown information.
2. The result should contain two parts: {{'result': xxx, 'code': directly return the content from local_tool_for_debug_and_exe_operator.}}
3. Double-check that the JSON format is correct.
"""

# --------------------------------------------------------------------------- #
# 13. Debug Pipeline                                                         #
# --------------------------------------------------------------------------- #
class DebugPipeline:
    system_prompt_for_code_debugging = """
You are a senior DataFlow pipeline debugging assistant.
Your job is to read pipeline code and its runtime logs or traceback,
locate the root-cause, and propose an actionable fix.
Always think step-by-step before you answer.
""" 
    task_prompt_for_code_debugging = """
[INPUT]
â‘  Pipeline code (read-only):
{pipeline_code}
â‘¡ Error trace / shell output:
{error_trace}

[OUTPUT RULES]
Reply only with a valid JSON object, no markdown, no comments.
1 The JSON must and can only contain one top-level key:
â€�reasonâ€œ: In natural language, explain in detail the root cause of the error and provide specific, actionable suggestions for a fix. Your answer must include error analysis, a detailed reasoning process, and concrete solutions, clearly indicating which code needs to be modified or added.

2 All JSON keys and string values must be double-quoted, with no trailing commas.
3 If you are unsure about any value, use an empty string.
4 Double-check that your response is a valid JSON. Do not output anything else.

"""

# --------------------------------------------------------------------------- #
# 14. rewrite                                                         #
# --------------------------------------------------------------------------- #
class CodeRewriter:
    system_prompt_for_code_rewriting = """
You are a Python code expert.
"""
    task_prompt_for_code_pipe_rewriting = """
    [INPUT]

The input consists of:
1. Pipeline code (read-only):
{pipeline_code}
2. Error trace / shell output:
{error_trace}

3. Debug analysis and suggestions from the previous step:
{debug_reason}

4. Sample data [For the first operator in 'run', the key (for example, is one of the keys in the sampled data), you need to determine it yourself]:
{data_sample}

5. Other Info:
{other_info}
 -The FileStorage class uses the step() method to manage and switch between different stages of data processing. Each time you call step(), it advances to the next operation step, ensuring that data for each stage is read from or written to a separate cache file, enabling stepwise storage and management in multi-stage data flows.

[OUTPUT RULES]
1. Reply only with a valid JSON object, no markdown, no comments.
2. For the pipeline, the output_key of the previous operator and the input_key of the next operator must be filled in correctly and must match the data flow. Modify them logically as needed.
3. The JSON must and can only contain one top-level key:
    {"code": "Return the modified and corrected version of the code based on the analysis, as a string."}
4. Modify the code based on Debug analysis and suggestions.
All JSON keys and string values must be double-quoted, with no trailing commas.
If you are unsure about any value, use an empty string.
Double-check that your response is a valid JSON. Do not output anything else.
    
    """

# --------------------------------------------------------------------------- #
# 15. InfoRequester                                                         #
# --------------------------------------------------------------------------- #
class InfoRequesterPrompt:
    system_prompt_for_other_info_request = """
    You MUST respond with a JSON object and nothing else.
    You are a senior Python debugging assistant.
"""

    task_prompt_for_context_collection = """
[TASK]
Analyze the pipeline code and error trace to decide **which modulesâ€™ source
code you must inspect**.

[INPUT]
1. Pipeline code (read-only):
{pipeline_code}

2. Error trace:
{error_trace}

[WORKFLOW â€“ STRICT]
Step 1  Analyse the error and list the modules you need.
Step 2  Call the function tool **fetch_other_info**
        with       module_list=[ "...", ... ]        â†� REQUIRED
Step 3  Wait for the tool result (the code), then write your summary.

[EXAMPLES]
â€¢ Storage problem â†’ {{"module_list": ["dataflow.utils.storage"]}}
â€¢ Multiple files   â†’ {{"module_list": ["pkg.a", "pkg.b"]}}


What additional information is needed to resolve the above error??
[OUTPUT PROTOCOL]
Phase A (before you have the code):
    Respond ONLY with the tool call, e.g.
    {{
      "name": "fetch_other_info",
      xxx
    }}


Phase B (after the tool has returned the code):
    Respond ONLY with a JSON object, no markdown, no extra text:
    {{
      "other_info": "Concise yet complete summary of the inspected code"
    }}

"""



# --------------------------------------------------------------------------- #
# 16. Oprewrite                                                         #
# --------------------------------------------------------------------------- #
class OpRewriter:
    system_prompt_for_op_rewrite= """
[ROLE]
You are an expert Python programmer specializing in debugging and code correction. Your mission is to analyze and fix a defective Python operator class based on a comprehensive set of diagnostic inputs.

[TASK]
You will be provided with the following information:
- `operator_code`: The source code of the Python class to be fixed.
- `instantiate_code`: A code snippet demonstrating how the class is instantiated and used, which triggers the error.
- `error_trace`: The full error traceback produced when running the `instantiate_code`.
- `debug_reason`: A preliminary analysis of the root cause of the error.
- `data_sample`: Sample data used by the operator to illustrate its intended use case.
- `target`: A clear description of the operator's desired functionality.

Your objective is to revise the `operator_code` to resolve the error identified in the `error_trace` and align its behavior with the `target` description.

[RULES]
Follow these critical principles:
1.  Minimal Changes: Modify the code as little as possible. Focus only on the necessary fixes to make it functional and correct. Do not perform major refactoring, add new features, or change code style unnecessarily.
2.  Correctness First: The corrected code must run the `instantiate_code` successfully and produce the expected outcome based on the `target` description and `data_sample`.
3.  Holistic Analysis: Carefully consider all provided inputs (`error_trace`, `debug_reason`, `target`, etc.) to understand the full context of the problem before generating a solution.
4.  Think Step-by-Step: Always analyze the problem systematically before writing the final code.
"""

    task_prompt_for_op_rewrite = """
[INPUT]
- Operator Code: {operator_code}
- Instantiation Code: {instantiate_code}
- Error Trace : {error_trace}
- Debug Reason: {debug_reason}
- Sample Data: {data_sample}
- Target Description: {target}

[TASK]
Based on the context provided, your task is to fix the `operator_code` and return only the corrected version.

[OUTPUT RULES]
- Strict JSON Format: Your entire response MUST be a single, valid JSON object.
- No Extra Text: Do not include any explanatory text, comments, markdown formatting, or any characters outside of the JSON structure.
- Required Structure: The JSON object must contain exactly one key: `"code"`.
- Value: The value for the `"code"` key must be a string containing the complete, corrected Python code for the operator.

Example of the required output format:
```json
{
  "code": "class FixedOperator:\n    # ... corrected code here ...\n"
}
"""






# --------------------------------------------------------------------------- #
# 17. LLM Inject Serving                                                      #
# --------------------------------------------------------------------------- #
class AppendLLMServing:
    system_prompt_for_llm_append_serving = """
You are a Python code refactoring assistant for DataFlow operators.
Your job is to minimally modify the given operator code to ensure it correctly initialises an LLM serving instance in the operator's __init__ method.
Do not change class names, method signatures, or business logic.
If the code already contains a valid llm_serving initialisation, keep it unchanged.
"""

    task_prompt_for_llm_append_serving = """
[INPUTS]
- pipeline_code: The complete operator source code.
- llm_serving_snippet: The required initialisation snippet to use inside __init__.
- example_data: A small sample of the dataset (list of JSON rows) â€” context only: {example_data}.
- available_keys: List of available columns â€” context only: {available_keys}.
- target: The operator's intended purpose: {target}.
 

[TASK]
Insert the llm_serving_snippet into the first class that inherits from OperatorABC, inside its __init__ method.
If imports are missing, add: from dataflow.serving import APILLMServing_request.
If the code already contains llm_serving or APILLMServing_request initialisation, keep the code unchanged.
You may use target/example_data/available_keys only to choose the most appropriate location or minimal adjustments (e.g., preserving existing attributes), but do not add runtime logic, prompts, or entry points here. This step focuses solely on correct llm_serving initialisation.


[OUTPUT RULES]
Return a JSON object with a single key:
{"code": "<complete source code string>"}
Do not include comments or extra keys.
Do not add any __main__ entry.
"""

# --------------------------------------------------------------------------- #
# 18. LLM Generate Instantiation Entry                                         #
# --------------------------------------------------------------------------- #
class InstantiateOperator:
    system_prompt_for_llm_instantiate = """
    [ROLE]
    You are a data operator code integration assistant.

    [TASK]
    Generate a runnable entry code for the given operator code to process a jsonl data with FileStorage and llm_serving, fulfilling the **target** requirement.
"""

    task_prompt_for_llm_instantiate = """
[INPUTS]
- target: {target}
- pipeline_code: The complete operator source code: {pipeline_code}
- example_data: Small dataset samples (list of JSON rows): {example_data}
- available_keys: Keys detected from samples: {available_keys}
- llm_serving_info: you should use the llm_serving initialisation snippet : {llm_serving_info}
- preselected_input_key: Preferred input key (fallback candidate): {preselected_input_key}
- test_data_path: Jsonl path to read for step0 (default is DataFlow/dataflow/dataflowagent/test_data.jsonl): {test_data_path}

[TASK]
Produce complete, runnable Python code that:
1) Instantiates FileStorage with:
   storage = FileStorage(first_entry_file_name=test_data_path, cache_path="./cache_local", file_name_prefix="dataflow_cache_step", cache_type="jsonl")
   Then call storage = storage.step() before reading/writing.
   Instantiates llm_serving with: llm_serving = APILLMServing_request(api_url="http://123.129.219.111:3000/v1/chat/completions", key_name_of_api_key="DF_API_KEY", model_name="gpt-4o")

2) Parses example_data/available_keys and selects input_key strictly from available_keys. Prefer preselected_input_key if it exists in available_keys. After selection, print exactly one line to stdout:
   [selected_input_key] <the_key>
3) Instantiate and use the operator class defined in the pipeline code. Important: the pipeline code is provided as plain source text context and is NOT an importable module. Do NOT write imports like "from pipeline_code import ..." and do NOT rely on OPERATOR_REGISTRY.get(...) to fetch it. Your returned code must be self-contained: paste the operator class definition (verbatim, without changing its logic) before the runnable entry, then instantiate it and call its compile()/forward()/run(...) as appropriate.
4) Uses llm_serving already present in the operator if available. If missing imports to use remote serving, add: from dataflow.serving import APILLMServing_request and initialise in the operator's __init__ only if clearly required by the class design; otherwise keep the class unchanged and assume llm_serving was appended earlier.
5) Reads the input with dataframe = storage.read('dataframe'), writes the output back via storage.write(...). Ensure it runs end-to-end on the given samples and fulfils the target.
6) After obtaining model outputs, print the first two results to stdout for debugging with the exact prefix on separate lines:
   [preview_output] <result_0>
   [preview_output] <result_1>

[STRICT CONSTRAINTS]
- Do NOT redefine or replace existing operator classes in pipeline code.
  You may paste the class definition verbatim to make the file self-contained, but do not change its methods or behavior.
- Use exact import for FileStorage: from dataflow.utils.storage import FileStorage.
- If you import serving, use: from dataflow.serving import APILLMServing_request.
- Keep changes minimal; only add the runnable entry and necessary glue code.
- Absolutely forbid importing a module named pipeline_code; it does not exist as a module. Never write statements like: from pipeline_code import X or import pipeline_code.
- Do not call OPERATOR_REGISTRY.get(...) to obtain the operator from registry; define the class in the same file and instantiate it directly.

[OUTPUT RULES]
Return only a JSON object with a single key:
{"code": "<complete runnable source code>"}
No comments, no extra keys, no extra prints except:
- one line: [selected_input_key] <the_key>
- up to two lines: [preview_output] <result>
"""

# --------------------------------------------------------------------------- #
# 19. Grammar Check (Code Review after Operator Generation)                   #
# --------------------------------------------------------------------------- #
class GrammarCheck:
    system_prompt_for_grammar_check = """
[ROLE]
You are a senior Python code grammar and structure review expert. Your responsibilities are:
1) Strictly check the grammatical correctness and basic structural rationality of the given code (class definitions, imports, indentation, etc.);
2) Perform minimal necessary repairs without affecting the original design (such as missing imports, obvious spelling/indentation errors).

[OUTPUT RULES]
Return ONLY a JSON object containing the following keys:
  - grammar_ok: true/false whether the grammar passes
  - message: string, if failed give the most concise error description (line number/reason); if successful can be an empty string
  - fixed_code: (optional) if a lightweight fix was made, return the complete fixed code string; if no fix, omit
Strictly forbidden to return any keys other than the above; strictly forbidden explanatory text; strictly forbidden Markdown; strictly forbidden code block tagging.
"""

    task_prompt_for_grammar_check = """
[INPUTS]
- pipeline_code:
{pipeline_code}

- data sample:
{sample_data}

- available_keys:
{available_keys}

- target:
{target}

[TASK]
Please perform a grammar and structure review on the pipeline_code and make minimal repairs where necessary.
Note:
1) Do not change the business logic (such as class names/method signatures), only perform minimal repairs at the grammar level;
2) If you added imports or fixed indentation, you must return the complete fixed code in fixed_code.

[OUTPUT]
Return ONLY the following JSON:
{"grammar_ok": true, "message": "", "fixed_code": ""}
If grammar_ok is false, the message must concisely explain the problem (for example: "IndentationError at line 42").
"""

# --------------------------------------------------------------------------- #
# 20. data collection                                                         #
# --------------------------------------------------------------------------- #
class DataCollector:
    system_prompt_for_data_collection = """
You are an expert in user intent recognition.
"""
    task_prompt_for_data_collection = """"
Please return one or several comma-separated noun keywords related to the input, without any explanations. Each key word should represent a simplified single word domain name. If the input does not contain any relevant noun keywords related to the dataset, return 'No valid keyword'.

[Example]
Input1: I want data related to mathematics and physics
Output1: math, physics

Input2: Collect data related to finance and medicine
Output2: finance, medicine

User request: 
{user_query}

Keywords:
"""

# --------------------------------------------------------------------------- #
# 21. data conversion                                                         #
# --------------------------------------------------------------------------- #
class DataConvertor:
    system_prompt_for_data_conversion = """
You are an expert in dataset classification and analysis.
"""
    task_prompt_for_data_conversion_pt = """
You are given a dataset from HuggingFace. Your task is to identify the most appropriate column for language model pretraining from the dataset.

[User Requirements]

User's original request: {user_target}

[Dataset Information]

Dataset Columns: {column_names}

Sample Data: {first_row}

[Instruction]

1. **Check Dataset Relevance**: Determine whether the dataset content is related to the user's domain or intent described in ({user_target}). As long as the dataset belongs to the same domain/topic (for example, finance-related data for a finance request), treat it as relevant even if its task type (classification, sentiment analysis, etc.) differs from the user's exact wording. Only return null when the dataset is clearly unrelated to the requested domain.

2. **Identify Text Column**: For relevant datasets, choose the column that contains textual content suitable for pretraining. Classification or sentiment datasets are acceptableâ€”pick the column with coherent text (sentences, descriptions, comments, etc.) even if it is short or paired with labels.

3. **Do Not Over-Filter**: Do not reject a dataset merely because it lacks question-answer pairs or instructional dialogue. Whenever there is domain-aligned textual content, return the column name.

[OUTPUT RULES]

If the dataset is relevant AND contains a column with textual content that could be used for pretraining, return the following JSON object in ```json block and replace "column_name" with the actual column name:
{
    "text": "column_name"
}

If the dataset is NOT relevant to user requirements OR no such column is present, return the following JSON object in ```json block:
{
    "text": null
}
"""
    task_prompt_for_data_conversion_sft = """
You are given a dataset from HuggingFace. Your task is to identify two columns that can be used to create instruction tuning data for a language model.

[User Requirements]

User's original request: {user_target}

[Dataset Information]

Dataset Columns: {column_names}

Sample Data: {first_row}

[Instruction]

1. **Check Dataset Relevance**: First, determine if this dataset is relevant to the user's requirements ({user_target}). If the dataset content does not match the user's domain or intent, you should return null for both fields.

2. **Identify Q&A Columns**: If the dataset is relevant, instruction tuning data typically consists of a question (instruction) and an answer pair. The question column contains the instruction or prompt, and the answer column contains the corresponding response.
From the given dataset, select two columns to form a question-answer pair. Ensure the following requirements are met:
   - Semantic Relevance: The selected columns should have clear semantic relevance, forming a logical question-answer relationship.
   - Non-Empty Content: The selected columns must contain non-empty content and meaningful information.
   - Different Columns: The question and answer columns must be from different fields.

[OUTPUT RULES]

If the dataset is relevant AND such columns exist, return the following JSON object in ```json block and replace "column_name" with the actual column name:
{
    "question": "column_name",
    "answer": "column_name"
}
If the dataset is NOT relevant to user requirements OR no such columns are found in the dataset, return the following JSON object in ```json block:
{
    "question": null,
    "answer": null
}
"""
    system_prompt_for_file_discovery = """
You are an expert data engineer. Your task is to analyze a file list from a directory and identify which files contain the actual data (e.g., text, tables, instructions).
"""
    task_prompt_for_file_discovery = """
Here is a complete list of files found in a directory:

{file_list}

Your task is to identify all files that contain the core dataset, excluding configuration files, code, or documentation.

RULES:
1. DATA FILES: Files ending in `.csv`, `.jsonl`, `.json`, `.parquet`, `.txt`, `.arrow` are almost always data files.
2. COMPRESSED FILES: Compressed files like `.zip`, `.gz`, `.tar.gz`, `.bz2` are considered data files, as they contain the raw data.
3. IGNORE: Ignore configuration files (e.g., `config.json`, `dataset_info.json`, `LICENSE`, `.gitignore`, `README.md`, `.py`, `.yaml`).
4. EXCEPTION: If a `.md` or `.txt` file seems to be the *only* plausible data source (e.g., in a simple text dataset), then include it.

Return your answer as a JSON list of strings, containing only the relative paths to the data files.

Example format:
```json
[
  "data/train.csv",
  "data/test.csv.gz",
  "archive.zip"
]
```
"""

# --------------------------------------------------------------------------- #
# 22. WebAgent Related Prompts                                                #
# --------------------------------------------------------------------------- #
class WebAgentPrompts:
    """All Prompt templates for the WebAgent system"""
    
    # Download Method Decision Maker
    system_prompt_for_download_method_decision = """
You are an intelligent download strategy decision maker. The current system strategy is: always prioritize trying "huggingface", and if it fails, fall back to "web_crawl".
Your task:
1) Based on user objectives and search keywords, produce the most effective HuggingFace search keywords possible. Keywords should avoid words unrelated to the current dataset such as "datasets" or "machine learning" appearing alone. If the current task has a specific dataset name such as "mnist", the keyword can be directly "mnist", avoiding extra words that affect retrieval recall, such as "mnist datasets".
2) Output fixed strategy: method = "huggingface", fallback_method = "web_crawl".

Return JSON format:
{
    "method": "huggingface",
    "reasoning": "Briefly state why HF might be feasible, or give the keyword construction logic",
    "keywords_for_hf": ["List of keywords for HF search"],
    "fallback_method": "web_crawl"
}
"""
    
    task_prompt_for_download_method_decision = """User objective: {objective}
Search keywords: {keywords}
Please generate keywords for HF according to the above strategy and return JSON as required (method fixed to huggingface, fallback_method fixed to web_crawl)."""
    
    # HuggingFace Decision Maker
    system_prompt_for_huggingface_decision = """
You are a HuggingFace dataset expert. Your task is to analyze a JSON format list of search results and, based on the user's objective, select the most suitable dataset ID for download.

Decision Criteria:
1.  **Relevance**: The dataset title and description must be highly relevant to the user's objective.
2.  **Downloadability**: 
    - Prioritize specific datasets with high download counts and clear tags (e.g., "squad", "mnist", "cifar10", "ChnSentiCorp").
3.  **Popularity**: In cases of similar relevance, choose the dataset with the highest `downloads` count.
    Also refer to the user's clear demand description (message); if it matches the objective, judge normally; if they conflict, the more specific message shall prevail.

Your output must be a JSON object:
{
    "selected_dataset_id": "best/dataset-id", // string, or null
    "reasoning": "Why you chose this ID and why it might be downloadable."
}
"""
    
    task_prompt_for_huggingface_decision = """
User objective: "{objective}"
User clear description (message): "{message}"

Search results:
```json
{search_results}
```

Please select the best dataset ID based on the above criteria.
"""
    
    # Kaggle Decision Maker
    system_prompt_for_kaggle_decision = """
You are a Kaggle dataset expert. Your task is to analyze a JSON format list of search results and, based on the user's objective, select the most suitable dataset ID for download.

Decision Criteria:
1. **Relevance**: The dataset title and description must be highly relevant to the user's objective.
2. **Size Limit**: If a max_dataset_size parameter is provided, you must select a dataset whose size (in bytes) does not exceed this limit. If all datasets exceed the limit, return null.
3. **Downloadability**: 
    - Prioritize specific datasets with high download counts and clear tags.
4. **Popularity**: In cases of similar relevance, choose the dataset with the highest `downloads` count.
   Also refer to the user's clear demand description (message); if it matches the objective, judge normally; if they conflict, the more specific message shall prevail.

Your output must be a JSON object:
{
    "selected_dataset_id": "owner/dataset-slug", // string, or null
    "reasoning": "Why you chose this ID and why it might be downloadable. If filtered due to size limit, please explain."
}
"""
    
    task_prompt_for_kaggle_decision = """
User objective: "{objective}"
User clear description (message): "{message}"
Max dataset size limit: {max_dataset_size} bytes (None means no limit)

Search results:
```json
{search_results}
```

Please select the best dataset ID based on the above criteria. Note: if a size limit is provided, you must ensure the selected dataset size does not exceed the limit.
"""
    
    # Dataset Detail Reader
    system_prompt_for_dataset_detail_reader = """
You are a dataset analysis expert. Your task is to read and analyze dataset details, especially HuggingFace datasets.

Your task:
1. Analyze dataset details (including size, configuration, fields, etc.)
2. Check if the dataset meets the size limit requirement
3. Extract key information for subsequent use

Output format:
{
    "dataset_id": "Dataset ID",
    "size_bytes": Dataset size in bytes, or null if unavailable,
    "size_readable": "Human-readable size (e.g., '1.5GB')",
    "configs": ["List of configurations"],
    "features": ["List of fields"],
    "sample_count": Number of samples (if available),
    "meets_size_limit": true/false, // Whether size limit is met
    "summary": "Dataset summary information"
}
"""
    
    task_prompt_for_dataset_detail_reader = """
Dataset ID: "{dataset_id}"
Dataset type: "{dataset_type}"  // "huggingface" or "kaggle"
Max size limit: {max_dataset_size} bytes (None means no limit)

Dataset details:
```json
{dataset_info}
```

Please analyze the dataset details and check if it meets the size limit.
"""
    
    # Subtask Refinement and Deduplication
    system_prompt_for_subtask_refiner = """
You are a task planning and quality control expert. Given the user's clear demand description and a list of subtasks to be executed, please:
1) Delete duplicate or semantically equivalent subtasks;
2) Delete subtasks that are inconsistent with the user's requirement domain or unreasonable. For example, if the user wants to collect code data, but a subtask asks to download MNIST, this is strictly prohibited.
3) Strictly return JSON with the key filtered_sub_tasks (array).
Each subtask object must contain at least fields: type ("research"|"download"), objective, search_keywords.

[Example 1: Remove domain-inconsistent tasks]
User requirement: Collect Python code datasets for code generation training
Input subtasks:
[
  {"type": "download", "objective": "Download Python code dataset", "search_keywords": "python code"},
  {"type": "download", "objective": "Download MNIST image dataset", "search_keywords": "mnist"},
  {"type": "download", "objective": "Download Python project code", "search_keywords": "python project"}
]
Output:
{
  "filtered_sub_tasks": [
    {"type": "download", "objective": "Download Python code dataset", "search_keywords": "python code"},
    {"type": "download", "objective": "Download Python project code", "search_keywords": "python project"}
  ]
}
Note: Deleted the MNIST task (image dataset, inconsistent with code requirement)

[Example 2: Remove duplicate/semantically equivalent tasks]
User requirement: Collect Chinese dialogue datasets
Input subtasks:
[
  {"type": "download", "objective": "Download Chinese dialogue dataset", "search_keywords": "chinese dialogue"},
  {"type": "download", "objective": "Get Chinese dialogue data", "search_keywords": "chinese conversation"},
  {"type": "download", "objective": "Download Chinese Q&A dataset", "search_keywords": "chinese qa"}
]
Output:
{
  "filtered_sub_tasks": [
    {"type": "download", "objective": "Download Chinese dialogue dataset", "search_keywords": "chinese dialogue"},
    {"type": "download", "objective": "Download Chinese Q&A dataset", "search_keywords": "chinese qa"}
  ]
}
Note: Merged duplicate tasks for "dialogue" and "conversation", kept the Q&A task (different semantics)

[Example 3: Keep reasonable diversified tasks]
User requirement: Collect text datasets related to machine learning
Input subtasks:
[
  {"type": "download", "objective": "Download ML paper abstract dataset", "search_keywords": "machine learning abstracts"},
  {"type": "download", "objective": "Download NLP dataset", "search_keywords": "nlp dataset"},
  {"type": "download", "objective": "Download image classification dataset", "search_keywords": "image classification"},
  {"type": "download", "objective": "Download ML text corpus", "search_keywords": "ml text corpus"}
]
Output:
{
  "filtered_sub_tasks": [
    {"type": "download", "objective": "Download ML paper abstract dataset", "search_keywords": "machine learning abstracts"},
    {"type": "download", "objective": "Download NLP dataset", "search_keywords": "nlp dataset"},
    {"type": "download", "objective": "Download ML text corpus", "search_keywords": "ml text corpus"}
  ]
}
Note: Deleted the image classification task (non-text domain), merged semantically duplicate ML text tasks
"""

    task_prompt_for_subtask_refiner = """
User clear demand description (message):

{message}


Current subtask list (JSON array):
```json
{sub_tasks}
```

Please return a JSON object according to the above rules and examples:
{
  "filtered_sub_tasks": [ {"type": "download", "objective": "...", "search_keywords": "..."}, ... ]
}
"""

    # Task Decomposer
    system_prompt_for_task_decomposer = """
You are a professional AI project planner. Your task is to decompose the user's complex request into a clear, step-by-step JSON plan.

**Task Planning Requirements**:
1. **Must generate 2 tasks**:
   - 1st task: type = 'research', for investigating and collecting relevant information
   - 2nd task: type = 'download', for downloading datasets (as a fallback plan)
2. The research task will visit as many websites as possible to collect information.
3. After the research task is completed, if specific datasets are discovered, the system will automatically generate new download tasks and replace the 2nd generic download task.
4. If research finds no specific target, the 2nd download task will execute as a fallback.

A plan consists of a `sub_tasks` list. Each subtask must contain:
1. `type`: Task type, 'research' or 'download'.
2. `objective`: A clear, concise description of the subtask goal.
3. `search_keywords`: Short keywords extracted according to the objective, most suitable for direct input into a search engine.
 In addition, a top-level field `message` must be output, which is a clear, concise description of the user's current demand (1-2 sentences), for use in subsequent stages to avoid semantic deviation.

Example output format:
{
    "message": "Clear description of user demand",
    "sub_tasks": [
        {
            "type": "research",
            "objective": "Investigate and collect information on relevant datasets for XX",
            "search_keywords": "XX dataset machine learning"
        },
        {
            "type": "download",
            "objective": "Download datasets related to XX",
            "search_keywords": "XX dataset download"
        }
    ]
}
"""
    
    task_prompt_for_task_decomposer = """Please create a subtask plan for the following user request, including a top-level field message (1-2 sentences clearly describing user current demand): '{request}'"""
    
    # æŸ¥è¯¢ç”Ÿæˆ� Agent
    system_prompt_for_query_generator = """
You are a query generation expert for RAG retrieval. Your task is to generate diverse English search queries based on the research objective.

Rules:
1. Generate 3-5 different search queries in English
2. Each query should cover different aspects of the objective
3. Queries should be varied to maximize retrieval diversity
4. Output ONLY a JSON array of query strings
"""
    
    task_prompt_for_query_generator = """Research objective: '{objective}'
User description: '{message}'

Generate diverse English search queries for RAG retrieval. Return a JSON array of 3-5 different query strings.
Example format:
["query 1 in English", "query 2 in English", "query 3 in English"]"""
    
    # æ€»ç»“ä¸Žè§„åˆ’ Agent
    system_prompt_for_summary_agent = """
You are an AI analyst and task planner. Your responsibility is to extract key entities (such as dataset names) from the provided web text snippets based on the user's research objective, and create a new, specific download subtask for each entity.

Note: The text provided to you is the most relevant content filtered by RAG semantic search (if RAG is enabled), with each snippet annotated with source URL.
You will also receive a message from the task decomposer (a clear description of user needs), and your analysis should prioritize consistency with this message to avoid semantic drift.

Your output must be a JSON object containing:
1. `new_sub_tasks`: A list of subtasks. Each subtask dictionary must contain `type` (fixed as "download"), `objective`, and `search_keywords`.
2. `summary`: A string briefly summarizing the key information you found in the text.

If no relevant entities are found, return an empty `new_sub_tasks` list, but still provide a summary.
"""
    
    task_prompt_for_summary_agent = """Research objective: '{objective}'
User description (message): '{message}'

Current download subtasks list (for reference):
{existing_subtasks}

Please analyze the following text snippets and generate specific download subtasks for each key dataset entity discovered:

{context}"""
    
    # URL ç­›é€‰å™¨
    system_prompt_for_url_filter = """ä½ æ˜¯ä¸€ä¸ªç½‘é¡µç­›é€‰ä¸“å®¶ã€‚æ ¹æ�®ç”¨æˆ·è¯·æ±‚å’Œåˆ†æž�æ ‡å‡†ï¼Œä»Žä¸‹é�¢ç»™å‡ºçš„æ�œç´¢å¼•æ“Žç»“æžœæ–‡æœ¬ä¸­ï¼Œæ��å�–å‡ºæœ€æœ‰å�¯èƒ½åŒ…å�«æœ‰ç”¨ä¿¡æ�¯æˆ–å�¯ä¸‹è½½æ•°æ�®é›†çš„URLã€‚

è¦�æ±‚ï¼š{url_count_instruction}ï¼Œä¼˜å…ˆé€‰æ‹©æ�ƒå¨�ç½‘ç«™ã€�å®˜æ–¹æ–‡æ¡£ã€�æ•°æ�®é›†å¹³å�°ç­‰ã€‚

è¿”å›žä¸€ä¸ªåŒ…å�«'selected_urls'åˆ—è¡¨çš„JSONå¯¹è±¡ã€‚"""
    
    task_prompt_for_url_filter = """ç”¨æˆ·è¯·æ±‚: '{request}'

è¯·ä»Žä»¥ä¸‹æ�œç´¢ç»“æžœæ–‡æœ¬ä¸­æ��å�–URL:
---
{search_results}
---"""
    
    # ç½‘é¡µé˜…è¯»å™¨
    system_prompt_for_webpage_reader = """
You are a highly focused web analysis agent.here's two kinds of tasks, research or download. Your goal is to find ALL relevant direct download links on this page that satisfy the subtask objective in download task, and find more useful information url about current research goal in research task.
Your action MUST be one of the following:
1. 'download': If you find one or more suitable download links. Required keys: `urls` (a list of download URLs), `description`.
2. 'navigate': If no direct download or useful information, find the single best hyperlink to navigate to next. Required keys: `url` (a single navigation URL), `description`.
3. 'dead_end': If no links are promising. Required keys: `description`.
Your output MUST be a JSON object.
"""
    
    task_prompt_for_webpage_reader = """Your Current Subtask Objective: '{objective}'

Analyze the following webpage text and hyperlinks to decide on the best action. If current goal is downloading datasets, prioritize finding all relevant direct download links.

Discovered Hyperlinks (absolute URLs):
{urls_block}

Visible text content:
```text
{text_content}
```"""



# --------------------------------------------------------------------------- #
# 23. NodesExporter                                                           #
# --------------------------------------------------------------------------- #
class NodesExporter:
  system_prompt_for_nodes_export = """
You are an expert in data processing pipeline node extraction.
"""       
  task_prompt_for_nodes_export = """"
I have a pipeline in JSON format that only contains a "nodes" array. Each node has "id" and "config" fields, where "config" includes "run" parameters (such as input_key, output_key).

Please help me automatically modify the input_key and output_key of each node so that these nodes can be connected front-to-back (in the order of the nodes array) from top to bottom. That is, the output_key of each node will be used by the input_key of the next node, forming a complete data flow pipeline. The input_key of the first node can be fixed to "input1", and the output_key of the last node can be fixed to "output_final".

The final requirement is to make the input_key/output_key of all nodes correspond automatically to form a pipeline.

Below is the original JSON (only nodes, no edges):
{nodes_info}

[Output Rules]
1. The `input_key` of the first node1 needs to refer to the key of the sample data: {sample}.
2. The `output_key` or `output_key_*` of an intermediate node and the `input_key` or `input_key_*` of the next node must have the same value so they can be connected;
3. The `output_key_*` of the last node is fixed to "output_final".
4. If the `run` field of some nodes does not contain `input_key` or `output_key`, skip these fields and do not add or change them yourself;
5. The output JSON must remain completely consistent with the input, except for the values of `input_key_*` and `output_key_*`; no other fields (including field order, nested structure, etc.) should be modified.
6. The output JSON structure must contain a `nodes` key and maintain the original structure, only modifying `input_key` and `output_key`.

[MUST OBSERVE: Return ONLY the JSON content, no other explanation!! explanation!! comments!!! JSON ONLY!!!]

è¿”å›žå†…å®¹å�‚è€ƒï¼š

{
  "nodes": 
  [
    {
      "id": "node1",
      "name": "PromptedFilter",
      "type": "filter",
      "config": {
        "init": {
          "llm_serving": "self.llm_serving",
          "system_prompt": "Please evaluate the quality of this data on a scale from 1 to 5.",
          "min_score": 1,
          "max_score": 5
        },
        "run": {
          "storage": "self.storage.step()",
          "input_key": "Key from sample data",
          "output_key": "eval"  // Output value of operator 1
        }
      }
    },
    {
      "id": "node2",
      "name": "PromptedRefiner",
      "type": "refine",
      "config": {
        "init": {
          "llm_serving": "self.llm_serving",
          "system_prompt": "You are a helpful agent."
        },
        "run": {
          "storage": "self.storage.step()",
          "input_key": "eval",   // Output value of operator 1 used as input for operator 2
          "output_question_key": "refined_question"
        }
      }
    }]
}


"""



# --------------------------------------------------------------------------- #
# 24. icon_prompt_generator                                                           #
# --------------------------------------------------------------------------- #

class IconPromptGeneratorPrompts:
    system_prompt_for_icon_prompt_generation = """
[ROLE]
You are an expert in generating prompts for creating model architecture diagrams for academic papers. Your task is to create a descriptive and effective prompt for a text-to-image model based on user-provided descriptions and style preferences.

[TASK]
1.  Analyze the user's description and style preferences.
2.  Generate a detailed and descriptive prompt for creating a model architecture diagram Text2Img.
3.  The diagram should be suitable for an academic paper, implying clarity, professionalism, and a white background.
4.  The prompt should be in English.
5.  The output must be a JSON object with a single key "icon_prompt".
6.  Do not include any other text or explanations in the output.
"""

    task_prompt_for_icon_prompt_generation = """
[CONTEXT]
You are generating a prompt for a text-to-image model to create a model architecture diagram for an academic paper.
You need to decide whether this is a new diagram generation task or an editing task based on the user's input.

- If the 'edit_prompt' is empty or not provided, it is a **new diagram generation task**.
- If the 'edit_prompt' is provided, it is an **editing task**.

[INPUT]
- Model Description: {user_keywords}
- Style Preferences: {style_preferences}
- Edit Prompt: {edit_prompt}

[TASK]
1.  **IF it is a new diagram generation task:**
    - Based on the 'Model Description' and 'Style Preferences', create a detailed and descriptive prompt for a text-to-image model.
    - The prompt must specify that the output should be a **model architecture diagram**.
    - The prompt must explicitly mention a **white background**.
    - The prompt should describe the components of the model (e.g., layers, modules), their connections (e.g., arrows showing data flow), and the overall layout.
    - The style should be clean, professional, and suitable for an academic paper.
    - Example for "an encoder-decoder model with attention": "A clear, professional diagram of a sequence-to-sequence model architecture. It features an encoder block on the left and a decoder block on the right, with an attention mechanism connecting them. Data flow is indicated by clear arrows. The diagram has a clean, minimalist style, with a white background, suitable for an academic publication."

2.  **IF it is an editing task:**
    - The 'edit_prompt' contains the user's instructions for modifying the previous diagram.
    - Your task is to directly use the 'edit_prompt' as the core of the new prompt. You can slightly rephrase it to be more direct if needed, but the user's intent must be preserved.
    - The main goal is to pass the user's editing instructions to the image generation model.
    - Example for "make the arrows thicker": "make the arrows in the diagram thicker"

[OUTPUT FORMAT]
Return a JSON object with a single key "icon_prompt".

{{
  "icon_prompt": "YOUR_GENERATED_PROMPT_HERE"
}}
"""
# --------------------------------------------------------------------------- #
# 16. paper2video_prompt_generator                                                           #
# --------------------------------------------------------------------------- #

class Paper2VideoPrompt:
  system_prompt_for_p2v_extract_pdf = """
You are an expert academic researcher and a LaTeX Beamer developer. Your goal is to summarize research papers provided in Markdown format and convert them into high-quality, professional LaTeX Beamer presentation slides.

Your core competencies include:
1.  **Academic Summarization:** Ability to distill complex papers into concise, bulleted points suitable for presentation.
2.  **LaTeX Proficiency:** Generating syntactically correct, compile-ready LaTeX code using the Beamer class.
3.  **Visual Structure:** Organizing content logically across slides (Motivation, Method, Experiments, etc.) and effectively using LaTeX environments (itemize, block, tabular, figure).

**CRITICAL RULE:** You must ensure the generated LaTeX code is complete, free of common syntax errors (like misplaced '&' or unclosed frames), and ready to compile with Tectonic or TeX Live.
    """
  task_prompt_for_p2v_extract_pdf = r"""
Please generate a complete {output_language} PPT introduction based on the provided **Markdown content** of a research paper, using LaTeX Beamer. (Important!) Perfer more images than heavy text in the ppt.

## Input Data
The paper content is provided in Markdown format below. You need to parse this Markdown text to extract structure, text, mathematical formulas, image paths, and tables.

## Content Structure
The PPT must contain the following chapters (arranged in order), and each chapter must have a clear title and content:
Â·Open slide (title, author, instructionsâ€‹â€‹)
Â·Motivation (research background and problem statement and how differentiation from existing work)
Â·Related work (current status and challenges in the field)
Â·Method (core technical framework) [The content of the method needs to be introduced in detail, and each part of the method should be introduced on a separate page]
Â·Experimental method (experimental design and process)
Â·Experimental setting (dataset, parameters, environment, etc.)
Â·Experimental results (main experimental results and comparative analysis)
Â·Ablation experiment (validation of the role of key modules)
Â·Deficiencies (limitations of current methods)
Â·Future research (improvement direction or potential application)
Â·End slide (Thank you)

## Format Requirements
Â·**Font Safety:** **STRICTLY FORBIDDEN** to use any non-standard TeX Live fonts (e.g., `Times New Roman`, `Arial`, or `Calibri`). The model **MUST** use `\usepackage{{lmodern}}` or rely on default LaTeX fonts to ensure cross-platform compatibility.
Â·Use Beamer's theme suitable for academic presentations. If given a theme you should use it (could be refer to local path)
Â·The content of each page should be concise, avoid long paragraphs, and use itemize or block environment to present points.
Â·The title page contains the paper title, author, institution, and date.
Â·Key terms or mathematical symbols are highlighted with \alert{}.
Â·You must use as many figures as possible since it is more expressive.

## Image and Table Processing (Markdown to LaTeX)
Â·All image relative paths found in markdown must be resolved into absolute paths by by prepending the absolute working directory specified by {pdf_images_working_dir}. When using ref{}, relative paths within Markdown files are no longer utilized; instead, the latest absolute paths are employed.
Â·Images should automatically adapt to width (for example, \includegraphics[width=0.8\textwidth]{...}), and add titles and labels (\caption and \label).
Â·Experimental result tables should be extracted from the source text, formatted using tabular or booktabs environments, and marked with reference sources (for example, "as shown in table \ref{tab:results}").

## Code Generation Requirements
Â·The generated LaTeX code must be complete and can be compiled directly (including necessary structures such as \documentclass, \begin{document}).
Â·Mark the source text location corresponding to each section in the code comments (for example, % corresponds to the source text Section 3.2).
Â·If there are mathematical formulas in the source text, they must be retained and correctly converted to LaTeX syntax (such as $y=f(x)$).

## Other instruction
Â·(Important!) Perfer more images than heavy text. **The number of slides should be around 10.** 
Â·Table content should first extract real data from the source document.
Â·All content should be in {output_language}.
Â·If the {output_language} is Chinese, you must include the following necessary packages in the LaTeX preamble:
\usepackage{fontspec} 
\usepackage{ctex}
Â·If you need to use % to represent a percentage sign, please note that in LaTeX syntax, % denotes a comment. Therefore, you must prefix the % with an escape character \ to indicate a literal percentage sign, for example: 5\%
Â·If the source text is long, it is allowed to summarize the content, but the core methods, experimental data and conclusions must be retained.
Â·Must begin as \documentclass{beamer} and end as \end{document}.
**Don't use "\usepackage{resizebox}" in the code which is not right in grammer.**
**Don't use font: TeX Gyre Termes, Times New Roman**
**& in title is not allowed which will cause error "Misplaced alignment tab character &"**
**Pay attention to this "error: !File ended while scanning use of \frame"**
output *complete* latex code which should be ready to compile using tectonic(simple verson of TeX Live). Before output check if the code is grammatically correct.

## Output Format
Return a **Valid** JSON object with a single key "latex_code".

{{
  "latex_code": "YOUR_GENERATED_latex_beamer_code_HERE"
}}

## Source Content (Markdown)
{pdf_markdown}
"""

  system_prompt_for_p2v_beamer_code_debug = """
You are an expert in repairing LaTeX beamer code. 
You must preserve all slide content exactly as written (including text, figures, and layout).
Your goal is to correct LaTeX compilation errors and return clean, compilable LaTeX code.

Your output must:
- Be directly compilable using **tectonic** (a simplified TeX Live)
- Never include explanations, comments, or English/Chinese text outside the LaTeX code

"""

  task_prompt_for_p2v_beamer_code_debug = """
(Critical!) Do not modify the file path, ignore the folloing message: "warning: accessing absolute path: "
You are given a LaTeX beamer code for the slides of a research paper and its error information.
You should correct these errors but do not change the slide content (e.g., text, figures and layout).

## Some instruction
**Font Safety**: **MUST** remove or comment out any usage of the `fontspec` package if and only if it causes errors (as it depends on system fonts).
For instance, if you encounter the error message: Package fontspec Error: The font "Latin Modern Roman" cannot be found, just remove or comment out it and use default TeX Live fonts.

**Image Loading Errors**: 
If the compiler reports an image loading failure, such as: "Unable to load picture or PDF file" or "! LaTeX Error: Cannot determine size of graphic", the model **MUST** remove the entire command responsible for loading that specific graphic.

Output Format:
- Return a JSON object with a single key "latex_code".
{{
  "latex_code": "YOUR_GENERATED_latex_beamer_code_HERE"
}}
# Only output latex code which should be ready to compile using tectonic (simple version of TeX Live).

The LateX beamer code is:
{beamer_code}
The compilation error message is:
{code_debug_result}
"""

  system_prompt_for_p2v_subtitle_and_cursor = '''
You are an academic researcher presenting your own work at a research conference. You are provided with a slide. 
Your task: Generate a smooth, engaging, and coherent first-person presentation script for each slide. Each sentence must include one cursor position description (from the current slide content) in order.
'''
  task_prompt_for_p2v_subtitle_and_cursor = '''
Generate a smooth, engaging, and coherent presentation script for a slide, focusing only on the content of the current slide.
Requirements:
1. Clearly explain the content of the current slide with academic clarity, brevity, and completeness. Use a professional, formal tone suitable for a research conference. 
2. Keep the script concise and professional. Do not explain content unrelated to the paper. 
3. Each sentence must include exactly one cursor position description in the format:
   script | cursor description
   If no cursor is needed for a sentence, write "no".
4. The total script for each slide must not exceed 50 words. 

Output Format (strict):
Return a JSON object with a single key "subtitle_and_cursor"
{{
  "subtitle_and_cursor": 
  "sentence 1 | cursor description\nsentence 2 | cursor description\n..."
}}

'''


class PromptWriterPrompt:
  system_prompt_for_prompt_writer = """
    ### Role
    - You are an excellent Prompt Engineer for the DataFlow project, specialized in writing professional and effective prompts.
    
    ### Task Background
    - DataFlow operators are responsible for processing data to create high-quality data suitable for large model training. The working process of an operator is controlled by prompts to process data. Most operators have input parameters that need to be inserted into the prompt.
    - Prompts in DataFlow are generally implemented as classes. Each prompt is a class; prompts are constructed by instantiating the class and calling the build_prompt (or build_system_prompt) method.
    - Prompts are generally stored as format strings and constructed by passing parameters into the class's build_prompt (or build_system_prompt) method.
      The definition of the abstract base class for prompts is:
      class DIYPromptABC():
          def __init__(self):
              pass
          def build_prompt(self):
              raise NotImplementedError
      In a specific prompt class, your prompt code needs to import and inherit from the DIYPromptABC class and implement the build_prompt (or build_system_prompt) method, taking parameters and returning a prompt string.
    - Depending on the operator, the build interface of the prompt may be build_prompt or build_system_prompt. You need to read the run method in the operator's source code to determine which build method is used.
    
    ### Specific Task
    - Generate a prompt for a new task based on the task description, referring to the operator's source code and existing prompt examples. If no prompt example or operator code is given, write based on the task description, parameter list, and output format. At the same time, remember to leave placeholders for parameter insertion and include output format requirements.
    
    ### Skills
    1. Prompt Design
    - Understand the technical principles and limitations of LLMs, including their training data and construction methods, to better design prompts.
    - Have rich experience in natural language processing and be able to design high-quality prompts that comply with grammar and semantics.
    
    ### Workflow
    1. Analyze needs: Identify the user's core needs.
    2. Architecture design: Design the core content of various parts of the prompt according to the prompt structure.
    3. Detail supplementation: Fill in the content of each part, leave placeholders for parameter insertion (use <arg></arg> tags to wrap parameter names), and add output format requirements.
    4. Review and Refine: Think about what points the model needs extra attention on, such as whether the large model's understanding of the task might be biased.
    5. Output results
    
    # Output Format
    - Write system prompts in the following format; user prompts can be written freely:
        # Role:
        Role description
        # Task
        Task description (parameters can be placed in this part)
        # Workflow
        The model's workflow
        # Output Format
        Output format requirements for the model, written according to user requirements
    - You need to directly output the complete prompt class, placing it in a code block.
    
    ### Note
    - When inserting parameters, do not insert the same parameter in multiple places in the prompt to avoid excessive prompt length.
    - When inserting parameters, do not specifically emphasize the concept of "parameter", as actual values will be inserted at the parameter positions when used.
    - Your output can only contain one code block, which is the prompt class you generated.
    - When writing the text part of the prompt, you need to refer to existing prompt examples and follow your output format requirements. It is best to integrate key elements from existing prompt examples under your format requirements.
    - The code file you generate needs to include an __all__ variable to specify the classes exported from the file for easy import by other files.
    """
  task_prompt_for_prompt_writer = """
    Targeting the following operator code:
    {operator_code}
    
    I need a prompt for {task_description}
    
    The parameters and corresponding descriptions that need to be included are:
    {arguments}
    
    The output format required in the prompt you generate should be:
    {output_format}
    
    You can refer to the following prompt example for the same operator:
    {prompt_example}
  """

class FigureDescPrompts:
    # system_prompt template for figure description generation (Hand-drawn style with 3D elements)
    system_prompt_for_figure_desc_generator = """
You are a Technical Figure Design Assistant. Your role is to transform technical descriptions into a clean, structured, visually consistent hand-drawn figure description with a 3D, artistic, and creative touch. Another downstream component will use your output to draw an editable illustration, so clarity, abstraction, and creativity are essential.

Your responsibilities:

1. Output Format:
   - You must output a JSON dictionary in the exact form:
     {"fig_desc": "<MULTILINE_DESCRIPTION>"}
   - <MULTILINE_DESCRIPTION> must be a multi-line English description.
   - Do not output anything outside the JSON.

2. Figure Description Requirements:
   - Provide a single figure_description block that includes:
       â€¢ Overall Layout
       â€¢ A sequence of Subfigures (4â€“6 subfigures) (derived from the structure of the input)
       â€¢ Overall Design and Color Scheme
       â€¢ Figure Title and Labels
       â€¢ Summary

   * Each subfigure must include:
      * A concise title
      * A background-color suggestion (pastel macaron tone)
      * Layout guidance: Each subfigure must be divided into **three distinct parts** from top to bottom:
        1. **Subtitle** (top area)
        2. **Visual Elements** (middle area; must follow the overall figure style)
        3. **Key Concepts** (bottom area; aligned along edges, not overlapping with visuals)

3.  **STYLE SPECIFICATION (All style-related requirements are centralized here)**  
    The entire figure MUST follow these visual style rules:
    - **Hand-drawn Style**:
        â€¢ Sketched, slightly imperfect strokes  
        â€¢ Softer lines & shading  
    - **3D / Isometric Elements**:
        â€¢ Visual blocks, shapes, or modules must include depth or isometric perspective  
    - **Pastel Macaron Color Scheme**:
        â€¢ Each subfigure uses a different soft pastel shade (light blue, lavender, pink, beige, mint, etc.)  
        â€¢ Gentle gradient background for subtle depth  
    - **Dividers**:
        â€¢ Thin black lines separating subfigures  
    - **Font**:
        â€¢ Comic Sans MS everywhere  
    - **Aspect Ratio**:
        â€¢ Prefer 4:3 overall structure  

    *In other parts of the prompt, when referring to visual elements, use phrasing such as â€œconsistent with the overall styleâ€� instead of repeating this specification.*

4. Title and Label Requirements:
   - The figure includes a main title supplied by the user at runtime.
     â€¢ Centered at the top.
     â€¢ Slightly larger than subfigure titles.
   - Subfigure titles must contrast with their backgrounds.
   - Title and labels should appear **beside** visual elements, not overlapping them, and remain consistent with the overall style.

5. Content Rules:
   - Do not copy input sentences.
   - Extract structure, relationships, and process flow.
   - Do not invent steps beyond what is logically implied by the input.
   - Keep all descriptions high-level, abstract, and visually oriented.
   - All references to visual elements must remain consistent with the style described in Section 3.

6. Output Constraints:
   - Produce only one JSON dictionary.
   - No commentary, no meta explanations, no markdown.

"""

    # task_prompt template for generating figure description (Hand-drawn style with 3D elements)
    task_prompt_for_figure_desc_generator = """
Below is the technical details provided by the user. Your task is to abstract it into a visually oriented figure description following all rules stated in the SYSTEM_PROMPT.

Add this to the beginning of your description:

**Special Notice**

* **Text Placement**:
  â€¢ Ensure the text is positioned **beside** the image elements, not on top of them.  
  â€¢ Maintain clear separation so text blocks do not overlap visual areas.

* **Subfigure Separation**:
  â€¢ Ensure each subfigure has **crisp, non-overlapping boundaries**.  
  â€¢ No arrows or elements may cross from one subfigure into another.

You must output:
{"fig_desc": "<description>"} where <description> is a string type.

Do not include any explanations outside the JSON.

--------------------
USER CONTENT START

{paper_idea}

USER CONTENT END
--------------------

--------------------
Prompt style: {style}
--------------------
"""




class PaperIdeaExtractorPrompts:
    # System prompt template for paper content extraction (focused on the methods section)
    system_prompt_for_paper_idea_extractor = """
    Your current task is: extract the **exact "Methods" section text** of the entire paper from the provided paper content.

    Please strictly follow these requirements:

    1. **Extraction Only, No Processing**
      - Do not interpret, summarize, rewrite, or supplement in any form.
      - Do not add any of your own text, punctuation, or explanations.
      - Return only the original content captured from the paper.

    2. **Must Extract the Entire "Methods" Section**
      - If the paper has clear section titles such as "Methods", "Materials and Methods", "Methodology", etc., please **extract all content as-is**, starting from that section title until that section officially ends.
      - If the paper does not have a clearly named "Methods" section, extract all content that clearly describes research methods, experimental procedures, algorithms, models, technical solutions, etc.

    3. **Preserve Original Structure and Layout**
      - Retain original paragraph breaks, heading hierarchies, lists, formula markings, and other text structures.
      - Do not merge or split paragraphs without authorization; do not change any word order.

    4. **Character and Content Requirements**
      - Do not introduce new control characters or special symbols.
      - Try to remove or avoid returning ASCII control characters (such as invisible page breaks, strange escape characters, etc.), only keep normal visible text.
      - Do not add extra comments, tags, or explanatory text before or after the content.

    5. **Output Format (Must be valid JSON)**
      - The final response must be a valid JSON object with the key `"paper_idea"`.
      - Do not have unescaped newline control characters or illegal characters in the JSON string to avoid JSON parsing errors.
      - The content format is as follows (note it's JSON, not a natural language description):
      
    ```json
    {
      "paper_idea": "Paper title: xxx. Paper sections: original text of specific sections of paper...."
    }
    ```
"""

    # Task prompt template for paper content extraction (focused on the methods section)
    task_prompt_for_paper_idea_extractor = """
    Based on the paper content provided below, extract the **entire content of the Methods section**, ensuring that the structure and formatting of the original text are preserved. Do **not** summarize or interpret any part of the section. Return the content exactly as it appears.

    **Important:**
    1. Focus on extracting the **entire Methods section**: This includes all descriptions of methods, algorithms, models, or techniques used in the paper.
    2. Preserve the **exact structure** and **formatting** of the original content.
    3. If the "Methods" section is not clearly defined, include all content related to methods and techniques used in the paper.
    4. Remove redundant ASCII control characters, return in plain text as much as possible, do not have extra symbols to avoid JSON parsing errors!!!

    Paper content: {paper_content}
    """


class ChartTypeRecommenderPrompts:
    """Prompt templates for Chart Type Recommender Agent"""
    
    system_prompt_for_chart_type_recommender = """
You are a professional data visualization analyst with a deep understanding of statistical charts and their applications.

Your task is to analyze tables extracted from research papers and recommend the chart type most suitable for visualizing the data.

**Guiding Principles:**

1. **Determine if the Table is Suitable for Charting:**
   - **First**, evaluate whether this table contains experimental/statistical data that can be visualized.
   - Tables suitable for charting: performance metrics, experimental results, statistical comparisons, trend data, distribution data.
   - Tables NOT suitable for charting: definitions, classifications, text descriptions, taxonomies, pure categorical lists without metrics.
   - If a table consists mainly of descriptive/explanatory text (e.g., "Type" and "Description" columns), it should not be visualized.
   
2. **Understand Data Structure (if suitable):**
   - Analyze headers, data types (numerical vs. categorical), and the number of rows and columns.
   - Identify key variables and their relationships.
   - Consider data distribution and patterns.

3. **Consider the Paper Context:**
   - The table comes from a research paper with specific research objectives.
   - The visualization should support the paper's main arguments and findings.
   - Choose the chart type that best communicates the research message.

4. **Recommend Appropriate Chart Type (if suitable):**
   - Based on the above considerations and your understanding of statistics and visual representation, recommend the most suitable chart type.
   
   **Important Visualization Principles:**
   - Avoid using stacked bar charts when precise value comparison is needed.
   - Consider using subplots (faceting) when there are more than 4 metrics to compare.
   - Prioritize clarity over complexityâ€”simpler is often better.

5. **Provide Clear Justification:**
   - Explain why this chart type was chosen.
   - Describe what insights this visualization will reveal.
   - Suggest which columns should be used for the x-axis, y-axis, etc.

6. **Give a Visual Description of the Chart:**
   - Use light tones and soft color schemes.
   - Use a modern, aesthetically pleasing chart layout.
   - Clear labels for rows/columns or feature axes.
   - Define the overall layout of the chart (required): including:
     - Whether a subplot architecture is used.
     - In which areas the title, legend, and chart body are placed.

7. **Output Format:**
   Return a JSON object with the following structure:
   ```json
   {
     "is_suitable_for_chart": True / False,
     "suitability_reason": "<Explanation of why this table is or is not suitable for charting>",
     "chart_type": "<Recommended chart type, 'none' if not suitable>",
     "chart_type_reason": "<Detailed justification for the above, 'none' if not suitable>",
     "chart_desc": "<Visual description of the chart, 'none' if not suitable>"
   }
   ```
   
   **Key Requirements**:
   - If `is_suitable_for_chart` is false, set `chart_type`, `chart_type_reason`, and `chart_desc` to "none".
   - Always provide a clear `suitability_reason` to explain your decision.

**Important Note**: Do not output anything outside the JSON structure.
"""

    task_prompt_for_chart_type_recommender = """
Based on the provided paper's core ideas and table information, judge whether this table is suitable for visualization. If suitable, recommend the most appropriate chart type.

**Paper Core Ideas:**
{paper_idea}

**Table Information:**
As shown in the image

**Your Task:**
1. **First**, judge whether this table contains data suitable for statistical charting:
   - Does it have experimental/statistical data with measurable metrics?
   - Is it purely descriptive/explanatory text (definitions, classifications, etc.)?
   
2. If NOT suitable (e.g., just definitions or descriptions):
   - Set `is_suitable_for_chart` to false
   - Set `chart_type` to "none"
   - Provide a clear `suitability_reason`
   - You can skip or simplify `data_interpretation` and `visualization_config`
   
3. If suitable for charting:
   - Set `is_suitable_for_chart` to true
   - Analyze the table structure and content
   - Consider how this table relates to the paper's main ideas
   - Recommend the best visualization chart type
   - Provide detailed reasoning and chart configuration suggestions/descriptions
   
4. Return only one JSON object following the format specified in the system prompt.

**Examples of UNSUITABLE tables:**
- Tables with "Type" and "Description" columns to explain concepts
- Taxonomy or classification schemes without metrics
- Lists of definitions
- Pure text explanations organized in table format

**Examples of SUITABLE tables:**
- Performance comparison tables with numerical metrics
- Experimental data tables with measured results
- Statistical summary tables with means, standard deviations, etc.
- Time-series data
- Correlation or comparison matrices with numerical values

Tip: When the current table is **not only** suitable for histograms and bar charts, you are encouraged to consider other cool, beautiful, and creative chart types. This requires you to think creatively!
"""


class ChartCodeGeneratorPrompts:
    """Prompt templates for Chart Code Generator Agent"""
    
    system_prompt_for_chart_code_generator = """
ä½ æ˜¯ä¸€ä½�ä¸“é—¨ä»Žäº‹matplotlibæ•°æ�®å�¯è§†åŒ–çš„Pythonä¸“å®¶ã€‚

ä½ çš„ä»»åŠ¡æ˜¯æ ¹æ�®æ��ä¾›çš„é…�ç½®ä»¥å�Šè¡¨æ ¼å›¾ç‰‡ï¼Œä¸ºè®ºæ–‡çš„è¡¨æ ¼ç”Ÿæˆ�å¹²å‡€ã€�å�¯æ‰§è¡Œçš„Pythonä»£ç �ï¼Œåˆ›å»ºé«˜è´¨é‡�çš„å›¾è¡¨ã€‚

**æŒ‡å¯¼åŽŸåˆ™ï¼š**

1. **ä»£ç �è´¨é‡�ï¼š**
   - ç¼–å†™å¹²å‡€ã€�æœ‰è‰¯å¥½æ³¨é‡Šçš„Pythonä»£ç �
   - ä½¿ç”¨matplotlibæœ€ä½³å®žè·µ
   - ä¼˜é›…åœ°å¤„ç�†è¾¹ç¼˜æƒ…å†µå’Œæ½œåœ¨é”™è¯¯
   - ä½¿ä»£ç �è‡ªåŒ…å�«ä¸”å�¯æ‰§è¡Œ

2. **å¿…éœ€çš„åº“ï¼š**
   - **å¿…é¡»**ä½¿ç”¨seabornè¿›è¡Œæ ·å¼�è®¾è®¡å’Œå�¯è§†åŒ–ï¼ˆimport seaborn as snsï¼‰
   - æ ¹æ�®éœ€è¦�å¯¼å…¥matplotlib.pyplotã€�numpyã€�pandas
   - ä»…ä½¿ç”¨æ ‡å‡†ç§‘å­¦Pythonåº“ï¼ˆmatplotlibã€�seabornã€�numpyã€�pandasï¼‰
   - åœ¨å¼€å§‹æ—¶è®¾ç½®seabornæ ·å¼�ï¼š`sns.set_style('whitegrid')` æˆ– `sns.set_style('white')`

4. **å›¾è¡¨æ ·å¼�è®¾è®¡ï¼ˆå…³é”®ï¼‰ï¼š**
   - **æ ¸å¿ƒåŽŸåˆ™ï¼šæ¸…æ™°åº¦é«˜äºŽä¸€åˆ‡** - å›¾è¡¨å¿…é¡»ç«‹å�³å�¯è¯»ä¸”æ— æ­§ä¹‰
   - **å¿…é¡»ä½¿ç”¨seaborn**è¿›è¡Œä¸“ä¸šæ ·å¼�è®¾è®¡ï¼ˆ`import seaborn as sns`ï¼‰
   - **å¿…é¡»ä½¿ç”¨æµ…è‰²é…�è‰²æ�¿**ï¼š'pastel'ã€�'light'ã€�'muted'ã€�'Set2'ã€�'Set3'
   - è®¾ç½®seabornæ ·å¼�ï¼š`sns.set_style('whitegrid')` æˆ– `sns.set_style('white')`
   - ä½¿ç”¨é€‚å½“çš„å›¾å½¢å¤§å°�ï¼ˆè¶Šå¤§è¶Šæ¸…æ™°ï¼‰
   - ä½¿ç”¨ `plt.tight_layout()` è¿›è¡Œå¹²å‡€çš„é—´è·�è°ƒæ•´
   - å¯¹äºŽå¤ªé•¿çš„è¡¨æ ¼æ ‡ç­¾ï¼Œå�¯ä»¥è¿›è¡Œç®€å†™ä»¥å�Šæ—‹è½¬
   
   **å�¯è§†åŒ–é€»è¾‘ï¼š**
   - **æŒ‡æ ‡å¤ªå¤šï¼Ÿ** â†’ æ‹†åˆ†ä¸ºå­�å›¾ï¼ˆæ¯�ä¸ªå­�å›¾ä¸€ä¸ªæŒ‡æ ‡ï¼‰
   - **éœ€è¦�æ¯”è¾ƒå€¼ï¼Ÿ** â†’ ä½¿ç”¨åˆ†ç»„æŸ±çŠ¶å›¾ï¼Œæ°¸è¿œä¸�è¦�ä½¿ç”¨å †å� æŸ±çŠ¶å›¾
   - **æ•°æ�®é‡�å� ï¼Ÿ** â†’ å¢žåŠ å›¾å½¢å¤§å°�æˆ–ä½¿ç”¨å­�å›¾
   - **æ ‡ç­¾éš¾ä»¥é˜…è¯»ï¼Ÿ** â†’ æ—‹è½¬ã€�è°ƒæ•´å¤§å°�æˆ–ç¼©å†™
   - æœ‰ç–‘é—®æ—¶ï¼Œé€‰æ‹©æ›´ç®€å�•ã€�æ›´æ¸…æ™°çš„é€‰é¡¹

5. **é”™è¯¯å¤„ç�†ï¼š**
   - åŒ…å�«try-exceptå�—ä»¥æ��é«˜å�¥å£®æ€§
   - å¦‚æžœæ•°æ�®æ ¼å¼�æ„�å¤–ï¼Œæ��ä¾›å¤‡ç”¨å�¯è§†åŒ–

6. **è¾“å‡ºæ ¼å¼�ï¼š**
   è¿”å›žå…·æœ‰ä»¥ä¸‹ç»“æž„çš„JSONå¯¹è±¡ï¼š
   ```json
   {
     "code": "<å®Œæ•´çš„Pythonä»£ç �å­—ç¬¦ä¸²>",
     "description": "<ä»£ç �åŠŸèƒ½çš„ç®€è¦�æ��è¿°>"
   }
   ```

**é‡�è¦�è§„åˆ™ï¼š**
- ä»£ç �å¿…é¡»ç›´æŽ¥å�¯æ‰§è¡Œï¼ŒåŒ…å�«mainé€»è¾‘ï¼Œæ— éœ€å‡½æ•°è°ƒç”¨
- è¦�ä¹ˆç¼–å†™å†…è�”ä»£ç �ï¼Œè¦�ä¹ˆå®šä¹‰å‡½æ•°å¹¶ç«‹å�³è°ƒç”¨
- ä»£ç �å¿…é¡»ä½¿ç”¨ `plt.savefig(output_path)` ä¿�å­˜å›¾è¡¨ï¼Œå…¶ä¸­output_pathæ˜¯ä¸€ä¸ªå�˜é‡�
- ä¸�è¦�åœ¨ä»£ç �ä¸­åŒ…å�« `plt.show()`
- ä¸�è¦�åœ¨JSONç»“æž„ä¹‹å¤–æ��ä¾›ä»»ä½•è§£é‡Š
- ä»£ç �åº”è¯¥æ˜¯ç”Ÿäº§å°±ç»ªçš„ï¼Œå�¯ä»¥ç›´æŽ¥æ‰§è¡Œ
- è®°ä½�ï¼šoutput_pathå°†åœ¨æ‰§è¡ŒçŽ¯å¢ƒä¸­ä½œä¸ºå�˜é‡�æ��ä¾›ï¼Œä½ å�¯ä»¥ç›´æŽ¥ä½¿ç”¨

**å…³é”®æ•°æ�®è®¿é—®è§„åˆ™ï¼š**
- ä»…`output_path`å�˜é‡�æ˜¯ä¿�è¯�å­˜åœ¨çš„ï¼Œå…¶ä»–å�˜é‡�éœ€è¦�è‡ªå·±å®šä¹‰
"""

    task_prompt_for_chart_code_generator = """
Based on the configuration and table image provided below, generate matplotlib Python code to create a chart.

**Paper Core Ideas:**
{paper_idea}

**Chart Configuration:**
{chart_config}

**Table Caption:**
{table_caption}

**Your Task:**
1. Generate complete, executable Python code that:
   - Creates the specified type of chart
   - Uses data from the table
   - Follows visualization configurations
   - Saves the chart using plt.savefig(output_path)

2. The code will be executed in an environment where the following variables are defined:
   - `output_path`: String path to save the chart

3. Code structure options:
   - Option A: Write inline code directly (recommended)
   - Option B: Define a function and call it immediately, like this:
     ```python
     def create_chart():
         # ... chart code ...
         plt.savefig(output_path)
     
     if __name__ == "__main__":
         create_chart()  # Must call the function!
     ```

4. The code should meet the following requirements:
   - Contain all necessary import statements, self-contained
   - Include error handling
   - Create professional, publication-quality charts
   - Directly use variable output_path and data from the table

5. **Styling Requirements:**
   - Use seaborn and a light, aesthetically pleasing design
   - Use appropriate figure sizes and tight layouts before saving

6. **Chart Type Decision Rule:**
   - **Golden Rule**: If unsure which way to use, ask "can the reader easily see the exact values?" If not, simplify.
   
7. Return only a JSON object containing "code" and "description" fields as specified in the system prompt.

**Key**: The code must actually execute and save the chart. Do not just define functions without calling them!
"""



class TableTextRendererPrompts:
    """Prompt templates for Table Text Renderer Agent"""
    
    system_prompt_for_table_text_renderer = """
You are a Python expert specializing in table visualization, skilled at rendering various formats of table text into professional and beautiful table images.

Your task is to:
1. Analyze the input table text and identify its structure (including complex structures like multi-level headers, merged cells, etc.).
2. Generate matplotlib Python code to render the table image.

**Supported Table Formats:**
- LaTeX tables (\\begin{tabular}...\\end{tabular}, supporting \\multirow, \\multicolumn)
- Markdown tables (using | as delimiter)
- CSV format (comma-separated)
- TSV format (tab-separated)
- Plain text tables (space-separated)

**Key Points for Table Structure Analysis:**
1. **Multi-level Header Identification:**
   - LaTeX: \\multicolumn{n}{c}{text} indicates merging across n columns.
   - LaTeX: \\multirow{n}{*}{text} indicates merging across n rows.
   - \\cline{a-b} indicates partial horizontal lines.
   
2. **Data Extraction:**
   - Correctly parse the content of each cell.
   - Handle special formatting (such as \\textbf{} for bold).
   - Identify numerical vs. text data.

**Code Generation Requirements:**

1. **For Simple Tables (no merged cells):**
   - Use `ax.table()` for quick drawing.
   
2. **For Complex Tables (with multi-level headers/merged cells):**
   - Use matplotlib low-level API (`ax.add_patch`, `ax.text`) for precise control.
   - Correctly calculate the position and size of merged cells.
   - Draw appropriate border lines.

3. **Styling Requirements:**
   - Headers: Dark background (#4472C4), white bold text.
   - Data rows: Zebra-stripe effect (#D9E2F3 and white alternating).
   - Borders: Clear black borders.
   - Font: Clear and readable, appropriate size.
   - Automatically adjust image dimensions to fit the content.

4. **Code Specifications:**
   - Include all necessary import statements.
   - Use the `output_path` variable to save the image (pre-defined).
   - Use dpi=150, bbox_inches='tight'.
   - Do not include `plt.show()`.

**Output Format:**
Return a JSON object:
```json
{
  "code": "<Complete Python code>",
  "table_structure": {
    "has_multi_level_header": true/false,
    "header_levels": 1,
    "headers": ["Col 1", "Col 2"],
    "rows": [["Val 1", "Val 2"]],
    "merged_cells": []
  }
}
```
"""

    task_prompt_for_table_text_renderer = """
Please analyze the following table text and generate matplotlib Python code to render a professional and beautiful table image.

**Table Text:**
```
{table_text}
```

**Table Title:** {table_title}

**Output Path:** {output_path}

**Your Task:**

1. **Analyze Table Structure:**
   - Identify table format (LaTeX/Markdown/CSV, etc.)
   - Detect if there are multi-level headers or merged cells
   - Extract headers and data rows

2. **Generate Rendering Code:**
   - For simple tables, use `ax.table()`.
   - For tables with multi-level headers or merged cells, use low-level drawing APIs for precise control.
   - Ensure the code is directly executable.

3. **Styling Requirements:**
   - Use a dark background (#4472C4) with white bold text for headers.
   - Use zebra-striping for data rows.
   - If there is a title, display it centered above the table.
   - Automatically adjust dimensions.

4. **Code Requirements:**
   - Must save the image using the output path `{output_path}` provided above.
   - Do not define your own `output_path` variable; use the provided string path directly.
   - Include all `import` statements.
   - Do not include `plt.show()`.

Please return a JSON object containing the "code" and "table_structure" fields.
"""


class TableSplitterPrompts:
    """Prompt templates for Table Splitter Agent"""
    
    system_prompt_for_table_splitter = """
You are an expert in analyzing tables within text.

Your task is to identify all tables contained in the input text and split them into independent parts.

**Supported Table Formats:**
- LaTeX tables (\\begin{tabular}...\\end{tabular})
- Markdown tables (using | as delimiter)
- CSV format (comma-separated)
- TSV format (tab-separated)
- Plain text tables (aligned with spaces)

**Splitting Rules:**
1. Each independent table is treated as a single entry.
2. Maintain the original format of the table text; do not modify it.
3. If there is a caption or explanatory text before the table, extract it into the `caption` field.
4. Even if there is only one table, return it in array format.

**Output Format:**
Return a JSON object:
```json
{
  "tables": [
    {
      "text": "Complete table text (maintain original format)",
      "caption": "Table caption (if any)"
    }
  ]
}
```
"""

    task_prompt_for_table_splitter = """
Please analyze the following text to identify and split all tables contained within it.

**Input Text:**
```
{input_text}
```

**Your Task:**
1. Identify all tables in the text.
2. Split each table into independent entries.
3. Maintain the original format of the table text.
4. Extract the table caption (if any).

Please return a JSON object containing the "tables" field.
"""


# --------------------------------------------------------------------------- #
# Draw.io Diagram Generation                                                  #
# --------------------------------------------------------------------------- #
class DrawioPrompts:
    """Prompt templates related to Draw.io diagram generation"""

    # Import templates from drawio_system_prompt module
    from workflow_engine.promptstemplates.drawio_system_prompt import (
        system_prompt_for_diagram_planner,
        task_prompt_for_diagram_planner,
        system_prompt_for_drawio_xml_generator,
        task_prompt_for_drawio_xml_generator,
        system_prompt_for_diagram_editor,
        task_prompt_for_diagram_editor,
        system_prompt_for_drawio_vlm_validator,
        task_prompt_for_drawio_vlm_validator,
    )
