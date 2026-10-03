"""MCP adapter schemas and protocol compatibility."""

import asyncio
import json
import os
from pathlib import Path
import sys
import subprocess

import pytest

from projectmapper.adapters.session import EXPOSED, NOT_EXPOSED
from projectmapper.mcp import _bound_resource, action_input_contracts, schema_contract_errors


def test_import_is_headless_and_does_not_require_the_optional_sdk():
    source_root = Path(__file__).resolve().parents[1]
    script = ("import sys; "
              f"sys.path.insert(0, {str(source_root / 'src')!r}); "
              "import projectmapper.mcp; "
              "assert 'tkinter' not in sys.modules")
    result = subprocess.run([sys.executable, "-c", script], cwd=source_root,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_schema_contracts_cover_the_controller_and_agent_allow_list():
    contracts = action_input_contracts()
    assert set(contracts) == set(EXPOSED) | set(NOT_EXPOSED)
    assert not schema_contract_errors()


def test_resource_text_is_bounded_in_utf8_bytes():
    result = _bound_resource("é" * 40, 64)
    assert len(result.encode("utf-8")) <= 64
    assert "Truncated" in result


def test_sdk_tools_and_resources_support_current_and_legacy_protocols(tmp_path):
    pytest.importorskip("mcp")
    try:
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters, stdio_client
    except ImportError:
        pytest.skip("MCP protocol exchange requires the optional SDK 2.x extra")

    (tmp_path / "example.txt").write_text("hello", encoding="utf-8")
    source_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    python_path = str(source_root / "src")
    if env.get("PYTHONPATH"):
        python_path += os.pathsep + env["PYTHONPATH"]
    env["PYTHONPATH"] = python_path

    async def exercise(mode):
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "projectmapper.mcp", "--root", str(tmp_path)],
            env=env,
            cwd=source_root,
        )
        with open(os.devnull, "w", encoding="utf-8") as errlog:
            transport = stdio_client(params, errlog=errlog)
            async with Client(transport, mode=mode) as client:
                first = await client.list_tools(cache_mode="refresh")
                second = await client.list_tools(cache_mode="refresh")
                if mode == "auto":
                    assert first.ttl_ms == 60_000
                    assert first.cache_scope == "private"
                assert [tool.name for tool in first.tools] == sorted(EXPOSED)
                assert [tool.name for tool in first.tools] == [tool.name for tool in second.tools]
                schemas = {tool.name: tool.input_schema for tool in first.tools}
                assert all("approved" not in schema.get("properties", {}) for schema in schemas.values())
                assert not any("approval" in name for name in schemas)
                assert schemas["text.open"]["required"] == ["path"]
                assert schemas["project.scan"]["properties"]["revision"]["type"] == "integer"
                assert schemas["text.save"]["properties"]["max_bytes"]["minimum"] >= 4096
                assert "backup" not in schemas["text.save"]["properties"]
                patch_types = schemas["patch.validate"]["properties"]["patch"]["anyOf"]
                assert {item["type"] for item in patch_types} == {"object", "string"}

                result = await client.call_tool("state.get", {})
                assert not result.is_error
                assert result.structured_content["status"] == "succeeded"
                assert Path(result.structured_content["data"]["root"]) == tmp_path

                tree = await client.read_resource("projectmapper://tree")
                if mode == "auto":
                    assert tree.ttl_ms == 0
                    assert tree.cache_scope == "private"
                rows = json.loads(tree.contents[0].text)
                assert any(row["relative_path"] == "example.txt" for row in rows["rows"])

                templates = await client.list_resource_templates(cache_mode="refresh")
                assert [item.uri_template for item in templates.resource_templates] == [
                    "projectmapper://snapshot/{projection}"
                ]

                compiled = await client.call_tool("snapshot.compile", {})
                assert not compiled.is_error
                snapshot = await client.read_resource("projectmapper://snapshot/tree")
                assert "example.txt" in snapshot.contents[0].text

    asyncio.run(exercise("auto"))
    asyncio.run(exercise("legacy"))
