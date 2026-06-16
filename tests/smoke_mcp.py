"""
Смоук-тест MCP-сервера через STDIO.

Запускает сервер как подпроцесс, шлёт initialize + tools/list,
проверяет что пришёл корректный JSON-RPC ответ.
"""

import asyncio
import json
import os
import sys

# Подменяем env ДО запуска сервера — ставим фейковый токен
# (сервер упадёт при первом реальном вызове, но handshake должен пройти)
os.environ["YANDEX_METRIKA_TOKEN"] = "test_fake_token_for_handshake"


async def send_message(proc, msg):
    """Шлёт JSON-RPC сообщение в stdin сервера."""
    line = json.dumps(msg) + "\n"
    proc.stdin.write(line.encode())
    await proc.stdin.drain()


async def read_message(proc, timeout=5.0):
    """Читает одну строку JSON-RPC ответа из stdout."""
    try:
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
    if not line:
        return None
    return json.loads(line.decode())


async def main():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "yandex_metrika_mcp.server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # 1. initialize
    await send_message(proc, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "smoke-test", "version": "0.1.0"},
        },
    })

    init_resp = await read_message(proc)
    assert init_resp is not None, "no initialize response"
    assert init_resp.get("id") == 1, f"wrong id: {init_resp}"
    assert "result" in init_resp, f"no result: {init_resp}"
    print(f"✅ initialize: server={init_resp['result']['serverInfo']}")

    # 2. initialized notification (без id, без ответа)
    await send_message(proc, {
        "jsonrpc": "2.0", "method": "notifications/initialized"
    })

    # 3. tools/list
    await send_message(proc, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}
    })
    tools_resp = await read_message(proc)
    assert tools_resp is not None, "no tools/list response"
    tools = tools_resp["result"]["tools"]
    print(f"✅ tools/list: {len(tools)} tools")
    for t in tools:
        print(f"   - {t['name']}")

    # 4. попробуем вызвать list_counters — должен вернуть ошибку 401, не краш
    await send_message(proc, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "list_counters", "arguments": {}},
    })
    call_resp = await read_message(proc, timeout=15)
    assert call_resp is not None, "no tools/call response"
    print(f"✅ tools/call list_counters (fake token): {call_resp['result']['content'][0]['text'][:150]}...")

    proc.terminate()
    await proc.wait()

    # покажем stderr — туда пишутся логи сервера
    err = await proc.stderr.read() if proc.returncode is None else b""
    print("\n--- stderr (server logs) ---")
    print((err or b"").decode()[-500:])


asyncio.run(main())
