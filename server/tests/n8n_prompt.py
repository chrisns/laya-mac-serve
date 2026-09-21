"""Rebuild the exact prompt that the n8n Text Classifier node sends.

The strings come from the node source:
packages/@n8n/nodes-langchain/nodes/chains/TextClassifier/{constants,processItem}.ts
"""

from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT_TEMPLATE = (
    "Please classify the text provided by the user into one of the following categories: "
    "{categories}, and use the provided formatting instructions below. Don't explain, and "
    "only output the json."
)

FORMAT_INSTRUCTIONS_HEAD = """You must format your output as a JSON value that adheres to a given "JSON Schema" instance.

"JSON Schema" is a declarative language that allows you to annotate and validate JSON documents.

For example, the example "JSON Schema" instance {"properties": {"foo": {"description": "a list of test words", "type": "array", "items": {"type": "string"}}}, "required": ["foo"]}}
would match an object with one required property, "foo". The "type" property specifies "foo" must be an "array", and the "description" property semantically describes it as "a list of test words". The items within "foo" must be strings.
Thus, the object {"foo": ["bar", "baz"]} is a well-formatted instance of this example "JSON Schema". The object {"properties": {"foo": ["bar", "baz"]}} is not well-formatted.

Your output will be parsed and type-checked according to the provided schema instance, so make sure all fields in your output match the schema exactly and there are no trailing commas!

Here is the JSON Schema instance your output must adhere to. Include the enclosing markdown codeblock:
"""


def json_schema(categories: list[tuple[str, str]], fallback: str = "discard") -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for name, description in categories:
        properties[name] = {
            "type": "boolean",
            "description": (
                f'Should be true if the input has category "{name}" (description: {description})'
            ),
        }
    if fallback == "other":
        properties["fallback"] = {
            "type": "boolean",
            "description": "Should be true if none of the other categories apply",
        }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
        "$schema": "http://json-schema.org/draft-07/schema#",
    }


def format_instructions(schema: dict[str, Any]) -> str:
    return FORMAT_INSTRUCTIONS_HEAD + "```json\n" + json.dumps(schema) + "\n```\n"


def system_message(
    categories: list[tuple[str, str]], multi_class: bool = False, fallback: str = "discard"
) -> str:
    schema = json_schema(categories, fallback)
    multi_class_prompt = (
        "Categories are not mutually exclusive, and multiple can be true"
        if multi_class
        else "Categories are mutually exclusive, and only one can be true"
    )
    fallback_prompt = {
        "other": 'If no categories apply, select the "fallback" option.',
        "discard": "If there is not a very fitting category, select none of the categories.",
    }[fallback]
    head = SYSTEM_PROMPT_TEMPLATE.replace("{categories}", ", ".join(name for name, _ in categories))
    return f"{head}\n\t{format_instructions(schema)}\n\t{multi_class_prompt}\n\t{fallback_prompt}"


def chat_request(
    text: str,
    categories: list[tuple[str, str]],
    multi_class: bool = False,
    fallback: str = "discard",
    model: str = "laya-typed-decisions",
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_message(categories, multi_class, fallback)},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
    }


OUTPUT_FIXING_TEMPLATE = """Instructions:
--------------
{instructions}
--------------
Completion:
--------------
{completion}
--------------

Above, the Completion did not satisfy the constraints given in the Instructions.
Error:
--------------
{error}
--------------

Please try again. Please only respond with an answer that satisfies the constraints laid out in the Instructions:"""


def output_fixing_message(instructions: str, completion: str, error: str) -> str:
    return (
        OUTPUT_FIXING_TEMPLATE.replace("{instructions}", instructions)
        .replace("{completion}", completion)
        .replace("{error}", error)
    )
