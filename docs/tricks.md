# Tricks

This page collects practical patterns for using `smartcomment`. All examples use the same small memory unit: a custom data class with an `id`, `content`, `timestamp`, and an unimportant field `run_id`.

```python
import json
from dataclasses import dataclass
from smartcomment import (
    IdentityRegistry,
    comment_graph,
    comment_link,
    comment_op,
    comment_variable,
    current_context,
)


@dataclass
class MemoryEntry:
    id: str
    content: str
    timestamp: str
    run_id: str
```

---

## 1. Use Strict Mode to Catch Snapshot Mismatches

By default, `smartcomment` allows the same identity to appear with a different snapshot and records it as a new version. When `strict` mode is enabled, `smartcomment` treats this as a potential instrumentation issue and raises an error instead.

**This is useful when you want to check whether your instrumentation is correct and ensure the completeness of the execution graph**.

```python
memory_v1 = MemoryEntry(
    id="mem-001",
    content="The user likes graph visualization.",
    timestamp="2026-06-01T10:00:00",
    run_id="run-a",
)

memory_v2 = MemoryEntry(
    id="mem-001",
    content="The user likes interactive graph visualization.",
    timestamp="2026-06-01T10:05:00",
    run_id="run-b",
)

with comment_graph(strict=True):
    comment_variable(
        memory_v1,
        id_strategy=lambda memory: memory.id,
        category="memory_entry",
        comment="The original memory entry.",
    )

    # This raises a trace consistency error because the identity is still
    # `"mem-001"`, but the encoded snapshot is different.
    comment_variable(
        memory_v2,
        id_strategy=lambda memory: memory.id,
        category="memory_entry",
        comment="A changed memory entry with the same id.",
    )
```

The error message is:

```text
TraceConsistencyError: Untraced mutation detected in strict mode.

  Variable name (identity)      : 'mem-001'
  Existing full node identifier : mem-001@1
  Existing version number       : v1

  Diff (first changed character with context):
    Recorded : MemoryEntry(id='mem-001', content='The user likes graph visualization.', timestamp='2026-06-01T10:00:00', run_id='run-a'...
    Provided : MemoryEntry(id='mem-001', content='The user likes interactive graph visualization.', timestamp='2026-06-01T10:05:00', ru...

The value bound to this identity has changed since it was last recorded, but no `comment_mutation` call was made. In strict mode this is treated as an error.

To fix this, either:
  1. Use `comment_mutation(target=rv, new_value=...)` to record the change explicitly.
  2. Disable strict mode: `comment_graph(strict=False)` or `graph.strict = False`.
```

---

## 2. Register a Custom Identity Strategy

Passing `id_strategy=lambda memory: memory.id` everywhere is repetitive. **For a custom type such as `MemoryEntry`, you can register a type-specific strategy once**:

```python
IdentityRegistry.register(
    MemoryEntry,
    lambda memory: memory.id,
    exist_ok=True,
)
```

After registration, `smartcomment` automatically uses the field `id` whenever it sees a `MemoryEntry` instance.

```python
with comment_graph(strict=True) as graph:
    comment_variable(
        memory_v1,
        category="memory_entry",
        comment="The original memory entry.",
    )

print(graph.to_runtime_graph().to_markdown())
```

The output is:

```text
## Graph

### Nodes (1)

**mem-001** (v1)
- Full Node ID: `mem-001@1`
- Value: `MemoryEntry(id='mem-001', content='The user likes graph visualization.', timestamp='2026-06-01T10:00:00', run_id='run-a')`
- Comment: The original memory entry.
- Category: memory_entry
- Created At: created in the system at `2026-06-01 21:03:35.908`
```

When `comment_variable` needs an identity strategy, `smartcomment` resolves it in a simple order. First, it uses the strategy explicitly provided to the call, such as `id_strategy=lambda memory: memory.id`. If no explicit strategy is provided, it checks whether the value's type has been registered in `IdentityRegistry`. This is why registering `MemoryEntry` above lets later calls omit `id_strategy`. If neither of these exists, `smartcomment` falls back to the built-in content-based strategy.

---

## 3. Use `encoding_fn` to Control Stored Snapshots

**An identity strategy decides the identity of a variable. `smartcomment` uses that identity to check whether the variable has already been added to the execution graph. Encoding controls a different thing: the snapshot stored for that variable**. By default, `smartcomment` stores `repr(value)`. For a custom data class, you may want a cleaner and more stable representation.

In this example, `run_id` is not important for tracing the memory unit itself. It may change from run to run, but it should not distract from the semantically important fields: `id`, `content`, and `timestamp`. We can define an encoding function that drops `run_id` and serializes the remaining fields as JSON.

```python
def encode_memory_entry(memory: MemoryEntry) -> str:
    return json.dumps(
        {
            "id": memory.id,
            "content": memory.content,
            "timestamp": memory.timestamp,
        },
        ensure_ascii=False,
        indent=4,
        sort_keys=True,
    )


with comment_graph(strict=True) as graph:
    comment_variable(
        memory_v1,
        encoding_fn=encode_memory_entry,
        category="memory_entry",
        comment="The original memory entry without run-specific metadata.",
    )

print(graph.to_runtime_graph().to_markdown())
```

The output is:

```text
## Graph

### Nodes (1)

**mem-001** (v1)
- Full Node ID: `mem-001@1`
- Value: `{
    "content": "The user likes graph visualization.",
    "id": "mem-001",
    "timestamp": "2026-06-01T10:00:00"
}`
- Comment: The original memory entry without run-specific metadata.
- Category: memory_entry
- Created At: created in the system at `2026-06-01 21:18:38.201`
```

With this encoding function, the graph stores a readable JSON snapshot and ignores `run_id`. This makes strict-mode comparisons focus on the fields that matter for the traced memory unit.

---

## 4. Reuse a Traced Variable and Its Configuration

Sometimes you need to reuse the same traced variable in later operations. If you call `comment_variable(..., to_runtime=True)`, it returns a read-only runtime handle instead of returning the original Python value.

That handle already knows the resolved identity, category, comment, and graph node. Passing the handle to `comment_op` or `comment_link` avoids repeating the same configuration.

```python
with comment_graph() as graph:
    memory_var = comment_variable(
        memory_v1,
        to_runtime=True,
        encoding_fn=encode_memory_entry,
        category="memory_entry",
        comment="A memory entry retrieved from the memory store.",
    )

    answer = "The user likes graph visualization."

    comment_op(
        op_name="answer_generation",
        category="generation",
        comment="Generate an answer using a retrieved memory entry.",
        inputs=[memory_var],
        outputs=[
            (
                answer,
                {
                    "category": "answer",
                    "comment": "The generated answer.",
                },
            ),
        ],
    )
```

The output is:

```text
## Graph

### Nodes (2)

**mem-001** (v1)
- Full Node ID: `mem-001@1`
- Value: `{
    "content": "The user likes graph visualization.",
    "id": "mem-001",
    "timestamp": "2026-06-01T10:00:00"
}`
- Comment: A memory entry retrieved from the memory store.
- Category: memory_entry
- Created At: created in the system at `2026-06-01 21:30:18.400`

**str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b** (v1)
- Full Node ID: `str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b@1`
- Value: `'The user likes graph visualization.'`
- Comment: The generated answer.
- Category: answer
- Created At: created in the system at `2026-06-01 21:30:18.414`

### Edges (1)

**Edge: `mem-001@1` -> `str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b@1`**
- Edge ID: `edge-00818ff6b2d244dda8dccca1a61cb6b3`
- Category: generation
- Comment: Generate an answer using a retrieved memory entry.
- Created At: created in the system at `2026-06-01 21:30:18.415`

### Operations (1)

**Op: answer_generation**
- Operation ID: `op-8f4191683b8a4eae9509db6e56c415d3`
- Category: generation
- Comment: Generate an answer using a retrieved memory entry.
- Created At: created in the system at `2026-06-01 21:30:18.414`
```

In this example, `memory_var` is a handle to the exact memory node that has just been added to the graph. The node is created with `encode_memory_entry`, so its stored snapshot is the cleaned JSON representation that ignores `run_id`. Later, when `memory_var` is passed to `comment_op`, `smartcomment` does not need to resolve the memory identity or repeat the encoding configuration again. It uses the existing traced node directly. **This keeps the code shorter and avoids accidentally tracing the same memory entry with a different configuration**.

---

## 5. Register a Variable in the Tracing Context

If several functions need the same traced variable, or if a later value is derived from it but you do not want to trace that derived value as a separate node, register the variable in the tracing context. To achieve this, you can use `variable_name` when calling `comment_variable`, then retrieve it later from `current_context()`.

```python
def retrieve_memory() -> MemoryEntry:
    memory = MemoryEntry(
        id="mem-001",
        content="The user likes graph visualization.",
        timestamp="2026-06-01T10:00:00",
        run_id="run-a",
    )
    comment_variable(
        memory,
        variable_name="retrieved_memory",
        encoding_fn=encode_memory_entry, 
        category="memory_entry",
        comment="The memory entry retrieved for the current request.",
    )
    return memory


def format_memory_for_prompt(memory: MemoryEntry) -> str:
    return f"{memory.content} (recorded at {memory.timestamp})"


def generate_answer(prompt_fragment: str) -> str:
    memory_var = current_context().get_variable("retrieved_memory")
    answer = "The user likes graph visualization."

    # We do not trace `prompt_fragment` as a separate variable. Instead, we link
    # the original memory entry directly to the answer. 
    comment_link(
        source=memory_var,
        target=(
            answer,
            {
                "category": "answer",
                "comment": "The generated answer.",
            },
        ),
        category="generation",
        comment="The answer is generated from the retrieved memory entry.",
    )
    return answer


with comment_graph() as graph:
    memory = retrieve_memory()
    prompt_fragment = format_memory_for_prompt(memory)
    answer = generate_answer(prompt_fragment)

    # Remove the temporary registration after the downstream functions no
    # longer need it.
    current_context().remove_variable("retrieved_memory")

print(graph.to_runtime_graph().to_markdown())
```

The output is:

```text
## Graph

### Nodes (2)

**mem-001** (v1)
- Full Node ID: `mem-001@1`
- Value: `{
    "content": "The user likes graph visualization.",
    "id": "mem-001",
    "timestamp": "2026-06-01T10:00:00"
}`
- Comment: The memory entry retrieved for the current request.
- Category: memory_entry
- Created At: created in the system at `2026-06-01 21:44:14.543`

**str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b** (v1)
- Full Node ID: `str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b@1`
- Value: `'The user likes graph visualization.'`
- Comment: The generated answer.
- Category: answer
- Created At: created in the system at `2026-06-01 21:44:14.557`

### Edges (1)

**Edge: `mem-001@1` -> `str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b@1`**
- Edge ID: `edge-a2f8e0dfeb73463a91c9ffc84c490a14`
- Category: generation
- Comment: The answer is generated from the retrieved memory entry.
- Created At: created in the system at `2026-06-01 21:44:14.558`

### Operations (1)

**Op: NONE sentinel**
- Operation ID: `__none_op__`
- Category: sentinel
- Created At: created in the system at `2026-06-01 21:44:14.558`
```

The `Op: NONE sentinel` appears because this example calls `comment_link` outside any explicit operation context. Every edge in `smartcomment` stores an `op_id`, so when no active operation is available, `smartcomment` creates a built-in sentinel operation and attaches the edge to it. **This does not correspond to a real operation in your program. It is only an internal placeholder used when an edge is created without an active operation**. If you want this edge to belong to a named operation, you can wrap the `comment_link` call in `comment_op_scope(...)` or use `comment_op(...)`.

---

## 6. Use `identity_only=True` for Lightweight or Changed Snapshots

Strict mode is useful, but sometimes a downstream operation only sees a lightweight or transformed representation of a memory unit. For example, a retrieval component may return a dictionary with the same memory `id`, but with `content` and `timestamp` merged into a new string.

That dictionary refers to the same memory unit, but its snapshot does not match the original `MemoryEntry` instance. In strict mode, this would normally raise a snapshot mismatch. 

Use `identity_only=True` when you only want to recover the existing memory node by identity, without replacing the stored snapshot or creating a new version from the current lightweight snapshot.

```python
retrieved_dict = {
    "id": "mem-001",
    "content": "The user likes graph visualization. Recorded at 2026-06-01T10:00:00.",
}

with comment_graph(strict=True):
    comment_variable(
        memory_v1,
        category="memory_entry",
        encoding_fn=encode_memory_entry,
        comment="The original memory entry with the full structured snapshot.",
    )

    memory_var = comment_variable(
        retrieved_dict,
        to_runtime=True,
        id_strategy=lambda memory: memory["id"],
        identity_only=True,
        comment=(
            "A lightweight retrieval result that refers to the existing memory "
            "entry by id."
        ),
    )

    print(memory_var.to_markdown())
```

The output is:

```text
**mem-001** (v1)
- Full Node ID: `mem-001@1`
- Value: `{
    "content": "The user likes graph visualization.",
    "id": "mem-001",
    "timestamp": "2026-06-01T10:00:00"
}`
- Comment: The original memory entry with the full structured snapshot.
- Category: memory_entry
- Created At: created in the system at `2026-06-01 22:05:27.354`
```

Here, `id_strategy=lambda memory: memory["id"]` maps the dictionary back to the same logical memory identity, `mem-001`. Because `identity_only=True`, the dictionary snapshot is used only for identity lookup. If a node with that identity already exists, `smartcomment` returns the existing node instead of raising a strict-mode mismatch or creating a new version.

---

## 7. Export and Import Graphs Across Processes

Sometimes you want to build an execution graph in one process and inspect or continue it in another process. For example, one script may instrument a memory system pipeline and save the graph, while a later notebook loads the graph for visualization or search.

```python
with comment_graph() as graph:
    comment_variable(
        memory_v1,
        encoding_fn=encode_memory_entry,
        category="memory_entry",
        comment="The memory entry traced in the first process.",
    )

with open("memory_trace.json", "w", encoding="utf-8") as f:
    json.dump(
        graph.export_graph(), 
        f, 
        ensure_ascii=False, 
        indent=4
    )
```

In another process, load the dictionary and reconstruct the graph with `ExecNetwork.import_graph(...)`.

```python
from smartcomment.runtime import ExecNetwork


with open("memory_trace.json", "r", encoding="utf-8") as f:
    graph_data = json.load(f)
graph = ExecNetwork.import_graph(graph_data)

print(graph.to_runtime_graph().to_markdown())
```

The output is:

```text
## Graph

### Nodes (1)

**mem-001** (v1)
- Full Node ID: `mem-001@1`
- Value: `{
    "content": "The user likes graph visualization.",
    "id": "mem-001",
    "timestamp": "2026-06-01T10:00:00"
}`
- Comment: The memory entry traced in the first process.
- Category: memory_entry
- Created At: created in the system at `2026-06-01 22:15:22.398`
```

You can also continue tracing on the imported graph:

```python
with comment_graph(graph=graph):
    answer = "The user likes graph visualization."
    comment_op(
        op_name="answer_generation",
        category="generation",
        comment="Generate an answer using the imported memory trace.",
        inputs=[
            comment_variable(
                memory_v1,
                to_runtime=True,
                encoding_fn=encode_memory_entry,
                identity_only=True,
            )
        ],
        outputs=[
            (
                answer,
                {
                    "category": "answer",
                    "comment": "The generated answer.",
                },
            ),
        ],
    )

print(graph.to_runtime_graph().to_markdown())
```

The output is:

```text
## Graph

### Nodes (2)

**mem-001** (v1)
- Full Node ID: `mem-001@1`
- Value: `{
    "content": "The user likes graph visualization.",
    "id": "mem-001",
    "timestamp": "2026-06-01T10:00:00"
}`
- Comment: The memory entry traced in the first process.
- Category: memory_entry
- Created At: created in the system at `2026-06-01 22:15:22.398`

**str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b** (v1)
- Full Node ID: `str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b@1`
- Value: `'The user likes graph visualization.'`
- Comment: The generated answer.
- Category: answer
- Created At: created in the system at `2026-06-01 22:19:24.344`

### Edges (1)

**Edge: `mem-001@1` -> `str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b@1`**
- Edge ID: `edge-68794afcd3d64eaa90ff42032e8964b6`
- Category: generation
- Comment: Generate an answer using the imported memory trace.
- Created At: created in the system at `2026-06-01 22:19:24.344`

### Operations (1)

**Op: answer_generation**
- Operation ID: `op-eecdff2c1b424bddb9f95f8733122df7`
- Category: generation
- Comment: Generate an answer using the imported memory trace.
- Created At: created in the system at `2026-06-01 22:19:24.343`
```

**When reusing an imported graph, make sure the identity and encoding strategies you use are consistent with the strategies used when the graph is first created. Otherwise, the same runtime object may be resolved differently in the new process**.

---

## 8. Use `class_name` to Separate Same-Content Variables

Sometimes two variables have the same content but different roles in the system. For example, consider a prompt template that asks a model to repeat the user's input. In that case, the user input and the model output may be exactly the same string.

If both values use the default content-based identity, `smartcomment` may resolve them to the same variable, because their content is identical. **This is usually not what you want: the user input and the model output are semantically different variables, even if their text is the same**. For this case, you can use `class_name` to namespace the variable identity:

```python
def repeat_input(prompt_template: str, user_input: str) -> str:
    return user_input


with comment_graph() as graph:
    prompt_template = "Repeat the user input exactly: {user_input}"
    user_input = "The user likes graph visualization."
    model_output = repeat_input(prompt_template, user_input)

    comment_op(
        op_name="llm_generation",
        category="llm_generation",
        comment="An LLM responds to a user's question.",
        inputs=[
            (
                prompt_template,
                {
                    "class_name": "prompt_template", 
                    "category": "prompt_template",
                    "comment": "The prompt template that asks the model to repeat the input.",
                }
            ),
            (
                user_input,
                {
                    "class_name": "user_input",
                    "category": "user_input",
                    "comment": "The original user input.",
                }
            ) 
        ],
        outputs=[
            (
                model_output,
                {
                    "class_name": "model_output",
                    "category": "model_output",
                    "comment": "The model output.",
                }
            )
        ],
    )

print(graph.to_runtime_graph().to_markdown())
```

The output is:
```text
## Graph

### Nodes (3)

**str:7c77680ccccb2079b8244166f313788aaad588b6** (v1) [prompt_template]
- Full Node ID: `prompt_template:str:7c77680ccccb2079b8244166f313788aaad588b6@1`
- Value: `'Repeat the user input exactly: {user_input}'`
- Comment: The prompt template that asks the model to repeat the input.
- Category: prompt_template
- Created At: created in the system at `2026-06-02 10:47:16.095`

**str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b** (v1) [user_input]
- Full Node ID: `user_input:str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b@1`
- Value: `'The user likes graph visualization.'`
- Comment: The original user input.
- Category: user_input
- Created At: created in the system at `2026-06-02 10:47:16.095`

**str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b** (v1) [model_output]
- Full Node ID: `model_output:str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b@1`
- Value: `'The user likes graph visualization.'`
- Comment: The model output.
- Category: model_output
- Created At: created in the system at `2026-06-02 10:47:16.095`

### Edges (2)

**Edge: `prompt_template:str:7c77680ccccb2079b8244166f313788aaad588b6@1` -> `model_output:str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b@1`**
- Edge ID: `edge-854815f33d60465c84b21ae288c5f72f`
- Category: llm_generation
- Comment: An LLM responds to a user's question.
- Created At: created in the system at `2026-06-02 10:47:16.096`

**Edge: `user_input:str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b@1` -> `model_output:str:a49c76c7ab6fc8aad410da8adf158826a62ffe1b@1`**
- Edge ID: `edge-46069a758e4b4cfbae17b38104836d35`
- Category: llm_generation
- Comment: An LLM responds to a user's question.
- Created At: created in the system at `2026-06-02 10:47:16.096`

### Operations (1)

**Op: llm_generation**
- Operation ID: `op-404b902eb91045e385a61def4924c777`
- Category: llm_generation
- Comment: An LLM responds to a user's question.
- Created At: created in the system at `2026-06-02 10:47:16.095`
```

With `class_name`, `smartcomment` prefixes the variable name with the namespace. Even if `user_input` and `model_output` have the same content-based identity, their full node identifiers become different.

---

## 9. Use the Execution Graph Query Interfaces

After a graph is built, it is more than a visualization artifact. You can use its query interfaces to inspect and slice the recorded trace. For example, you can retrieve variables, operations, edges, and sessions; search them by category or name; filter subgraphs by time, category, operation, or session; and run graph traversals such as ancestor or descendant queries. For concrete end-to-end usage, see the [MemTrace](https://github.com/zjunlp/MemTrace) source code.


