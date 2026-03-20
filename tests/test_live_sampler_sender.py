import asyncio

import httpx
from anticheat_sdk import LiveSamplerSender


def test_live_sampler_sender_batches_and_flushes() -> None:
    requests: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/batch"):
            payload = request.read().decode()
            requests.append(("batch", httpx.Response(200, text=payload).json()))
            return httpx.Response(200, json={"status": "ok"})
        if request.method == "POST" and request.url.path.endswith("/flush"):
            requests.append(("flush", {}))
            return httpx.Response(200, json={"status": "ok", "flushed": 0, "buffered": 0})
        if request.method == "GET" and request.url.path.endswith("/status"):
            requests.append(("status", {}))
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "buffered": 0,
                    "files_written": 1,
                    "output_dir": "/tmp/live",
                },
            )
        return httpx.Response(404, json={"status": "not_found"})

    async def run_case() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://local") as client:
            sender = LiveSamplerSender(
                game_id="g1",
                server_id="s1",
                gateway_url="http://local",
                player_id="p1",
                session_id="sess1",
                batch_size=2,
                flush_interval_seconds=999,
                http_client=client,
            )
            first = await sender.enqueue_event("player_moved", {"speed": 300}, label="clean")
            second = await sender.enqueue_event(
                "hit_registered",
                {"hit_zone": "head"},
                label="suspicious",
            )
            assert first["flushed"] == 0
            assert second["flushed"] == 2
            assert second["buffered"] == 0
            await sender.force_flush_remote()
            status = await sender.status()
            assert status["status"] == "ok"
            await sender.close()

    asyncio.run(run_case())
    batch_calls = [item for item in requests if item[0] == "batch"]
    assert len(batch_calls) == 1
    assert len(batch_calls[0][1]["events"]) == 2
    assert any(item[0] == "flush" for item in requests)
    assert any(item[0] == "status" for item in requests)
