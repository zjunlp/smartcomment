# Quick Start

This page shows the simplest way to use `smartcomment`: decorate a function with `comment_fn`. Compared with manual tracing, `comment_fn` does not require you to explicitly create variables or operations. It automatically records a function call as an operation, treats the function arguments as input variables, and treats the return value as the output variable.

We will build a tiny dummy OpenAI-style interface and trace calls to it.

---

## 1. A Dummy OpenAI Interface

The dummy interface exposes a `__call__` method. For any `messages` input, it returns the same response:

```python
class DummyOpenAI:
    """A tiny synchronous OpenAI-style client used for the quick start."""

    def __call__(self, messages: list[dict[str, str]]) -> str:
        return "You can use `smartcomment` to record a funcation call."


class AsyncDummyOpenAI:
    """A tiny asynchronous OpenAI-style client used for the quick start."""

    async def __call__(self, messages: list[dict[str, str]]) -> str:
        return "You can use `smartcomment` to record a funcation call."
```

---

## 2. Trace a Synchronous Function Call

First, create a small wrapper function around the dummy client and decorate it with `comment_fn`.

```python
from smartcomment import (
    comment_fn,
    comment_graph,
    comment_session,
)


client = DummyOpenAI()


@comment_fn(
    op_name="dummy_openai.generate",
    comment="Generate a deterministic dummy response from chat messages.",
    category="llm_call",
    op_metadata={
        "provider": "dummy-openai",
        "model": "dummy-chat-model",
        "temperature": 0.0,
    },
)
def generate_response(messages: list[dict[str, str]]) -> str:
    """Call the synchronous dummy OpenAI client."""
    return client(messages)
```

Now run the decorated function inside a graph context.

```python
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "How do I record a function call?"},
]

with comment_graph() as graph:
    with comment_session() as session:
        response = generate_response(messages)

runtime_graph = graph.to_runtime_graph()
print(runtime_graph.to_markdown(include_metadata=True))
```

The output is:

```text
## Graph

### Nodes (2)

**list:f6aec3640a5ed939fd8623fca8fd54fbde0d19ed** (v1)
- Full Node ID: `list:f6aec3640a5ed939fd8623fca8fd54fbde0d19ed@1`
- Value: `[{'role': 'system', 'content': 'You are a helpful assistant.'}, {'role': 'user', 'content': 'How do I record a function call?'}]`
- Category: variable
- Created At: created in the system at `2026-06-01 14:08:56.471`

**str:bec801153e4d0f5ee0bd7415f0cb7ac31d9f93d5** (v1)
- Full Node ID: `str:bec801153e4d0f5ee0bd7415f0cb7ac31d9f93d5@1`
- Value: `'You can use `smartcomment` to record a funcation call.'`
- Category: variable
- Created At: created in the system at `2026-06-01 14:08:56.471`

### Edges (1)

**Edge: `list:f6aec3640a5ed939fd8623fca8fd54fbde0d19ed@1` -> `str:bec801153e4d0f5ee0bd7415f0cb7ac31d9f93d5@1`**
- Edge ID: `edge-13bc2499ea4946738e9f634295a14793`
- Category: llm_call
- Comment: Generate a deterministic dummy response from chat messages.
- Created At: created in the system at `2026-06-01 14:08:56.471`
- Metadata: `{"provider": "dummy-openai", "model": "dummy-chat-model", "temperature": 0.0}`

### Operations (1)

**Op: dummy_openai.generate**
- Operation ID: `op-e7897a73000743669e27428acee1cad2`
- Category: llm_call
- Comment: Generate a deterministic dummy response from chat messages.
- Created At: created in the system at `2026-06-01 14:08:56.470`
- Metadata: `{"provider": "dummy-openai", "model": "dummy-chat-model", "temperature": 0.0}`
```


In this example, we attach metadata to the operation through `op_metadata`, including the dummy model name and the temperature used for generation. When rendering the graph as Markdown, we pass `include_metadata=True` so that these metadata fields are shown on the operation and its dependency edge.

Note that we did not pass `id_strategy`. In this case, `smartcomment` uses the default content-based identity strategy. It creates a deterministic identity from the value's content, so the same JSON-like message list will be recognized as the same traced variable if it appears again with the same content.

---

## 3. What `comment_fn` Records

`comment_fn` is the most convenient tracing API because it follows the natural shape of a Python function call, minimizing instrumentation overhead and code changes.

```python
@comment_fn(...)
def f(x, y):
    return z
```

When `f(x, y)` is called inside `comment_graph`, `smartcomment` records:

- An operation representing the function call.
- Input variables for `x` and `y`.
- An output variable for `z`.
- Dependency edges from each input variable to the output variable.

---

## 4. Trace an Asynchronous Function Call

`comment_fn` also supports asynchronous functions. The usage is almost the same.

```python
import asyncio


async_client = AsyncDummyOpenAI()


@comment_fn(
    category="llm_call",
    op_metadata={
        "provider": "dummy-openai",
        "model": "dummy-chat-model",
        "temperature": 0.0,
    },
)
async def async_generate_response(messages: list[dict[str, str]]) -> str:
    """Call the asynchronous dummy OpenAI client."""
    return await async_client(messages)


async def main() -> None:
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Can smartcomment trace async calls?"},
    ]

    with comment_graph() as graph:
        with comment_session():
            response = await async_generate_response(messages)

    runtime_graph = graph.to_runtime_graph()
    print(runtime_graph.to_markdown(include_metadata=True))

asyncio.run(main())
```

The output is:

```text
## Graph

### Nodes (2)

**list:1d6ec1568e1e66c2d87daa731a480d29c316944c** (v1)
- Full Node ID: `list:1d6ec1568e1e66c2d87daa731a480d29c316944c@1`
- Value: `[{'role': 'system', 'content': 'You are a helpful assistant.'}, {'role': 'user', 'content': 'Can smartcomment trace async calls?'}]`
- Category: variable
- Created At: created in the system at `2026-06-01 14:12:18.266`

**str:bec801153e4d0f5ee0bd7415f0cb7ac31d9f93d5** (v1)
- Full Node ID: `str:bec801153e4d0f5ee0bd7415f0cb7ac31d9f93d5@1`
- Value: `'You can use `smartcomment` to record a funcation call.'`
- Category: variable
- Created At: created in the system at `2026-06-01 14:12:18.266`

### Edges (1)

**Edge: `list:1d6ec1568e1e66c2d87daa731a480d29c316944c@1` -> `str:bec801153e4d0f5ee0bd7415f0cb7ac31d9f93d5@1`**
- Edge ID: `edge-f4caa10648944616b3d9f671bc212965`
- Category: llm_call
- Comment: [async_generate_response] Call the asynchronous dummy OpenAI client.
- Created At: created in the system at `2026-06-01 14:12:18.266`
- Metadata: `{"provider": "dummy-openai", "model": "dummy-chat-model", "temperature": 0.0}`

### Operations (1)

**Op: async_generate_response**
- Operation ID: `op-82280b988b5340f8835281c8abf55ef4`
- Category: llm_call
- Comment: [async_generate_response] Call the asynchronous dummy OpenAI client.
- Created At: created in the system at `2026-06-01 14:12:18.265`
- Metadata: `{"provider": "dummy-openai", "model": "dummy-chat-model", "temperature": 0.0}`
```

For this example, we do not explicitly provide the operation comment or operation name. **In this case, `smartcomment` automatically uses the function's docstring as the operation comment and the function name as the operation name. This is useful when the function name and docstring already describe the operation clearly**.

---

## 5. Configure Inputs and Outputs

So far, the auto-created input and output variables use default options. You can customize a specific input parameter, or the output, through `param_options`. It maps a parameter name to an option dictionary whose keys (such as `category`, `comment`, `id_strategy`) override the shared defaults for that variable only. The reserved key `"-o"` targets the output variable instead of an input parameter.

The example below configures the `messages` input with its own `category` and `comment`, and configures the output with its own `category` and `comment`.

```python
@comment_fn(
    op_name="dummy_openai.generate",
    comment="Generate a deterministic dummy response from chat messages.",
    category="llm_call",
    op_metadata={
        "provider": "dummy-openai",
        "model": "dummy-chat-model",
        "temperature": 0.0,
    },
    param_options={
        "messages": {
            "category": "chat_messages",
            "comment": "The chat messages sent to the dummy OpenAI client.",
        },
        "-o": {
            "category": "chat_completion",
            "comment": "The completion returned by the dummy OpenAI client.",
        },
    },
)
def generate_response(messages: list[dict[str, str]]) -> str:
    """Call the synchronous dummy OpenAI client."""
    return client(messages)
```

Run it the same way as before:

```python
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Can I use `smartcomment` to record a function call?"},
]

with comment_graph() as graph:
    with comment_session() as session:
        response = generate_response(messages)

runtime_graph = graph.to_runtime_graph()
print(runtime_graph.to_markdown(include_metadata=True))
```

The output is:

```text
## Graph

### Nodes (2)

**list:b95906d21e162d90dc6d86a502932fc3f6e10861** (v1)
- Full Node ID: `list:b95906d21e162d90dc6d86a502932fc3f6e10861@1`
- Value: `[{'role': 'system', 'content': 'You are a helpful assistant.'}, {'role': 'user', 'content': 'Can I use `smartcomment` to record a function call?'}]`
- Comment: The chat messages sent to the dummy OpenAI client.
- Category: chat_messages
- Created At: created in the system at `2026-06-01 15:02:41.590`

**str:bec801153e4d0f5ee0bd7415f0cb7ac31d9f93d5** (v1)
- Full Node ID: `str:bec801153e4d0f5ee0bd7415f0cb7ac31d9f93d5@1`
- Value: `'You can use `smartcomment` to record a funcation call.'`
- Comment: The completion returned by the dummy OpenAI client.
- Category: chat_completion
- Created At: created in the system at `2026-06-01 15:02:41.590`

### Edges (1)

**Edge: `list:b95906d21e162d90dc6d86a502932fc3f6e10861@1` -> `str:bec801153e4d0f5ee0bd7415f0cb7ac31d9f93d5@1`**
- Edge ID: `edge-2342e9fee69844a4bc69294f1afd9ee8`
- Category: llm_call
- Comment: Generate a deterministic dummy response from chat messages.
- Created At: created in the system at `2026-06-01 15:02:41.590`
- Metadata: `{"provider": "dummy-openai", "model": "dummy-chat-model", "temperature": 0.0}`

### Operations (1)

**Op: dummy_openai.generate**
- Operation ID: `op-d4b9cb783ce8493c8bf29ec10232c624`
- Category: llm_call
- Comment: Generate a deterministic dummy response from chat messages.
- Created At: created in the system at `2026-06-01 15:02:41.589`
- Metadata: `{"provider": "dummy-openai", "model": "dummy-chat-model", "temperature": 0.0}`
```

---

**Next:** [Visualization →](visualization.md)