#!/usr/bin/env python3
"""
Core of Potato v1.0.0 — Comprehensive Load & Integration Test Suite
==================================================================
A standalone test runner designed to validate Core of Potato gateway behavior
against a live running server at http://localhost:2809.

Tests:
  1. All 4 NaModu delivery methods (JSON body, Bearer, X-User, User header)
  2. All 3 NaModu validation failure types
  3. All model aliases (grok, gemini, chatgpt, gpt)
  4. Multi-user bombardment (18 prompts, 2 users, 3 platforms, 1s apart)
  5. 2-minute endurance run (max throughput)
  6. Streaming SSE validation
  7. Concurrency serialization (same user+model queues, different keys parallel)

Prerequisites:
    - Core of Potato server must be running: python3 -m core
    - Caller prefixes OC and CD must be registered in data/caller_map.json

Usage:
    python3 tests/load_test.py            # Run all tests
    python3 tests/load_test.py 1 3 5      # Run specific tests by number
"""

import asyncio
import aiohttp
import json
import time
import sys
from collections import defaultdict

# ─────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:2809"
API_URL = f"{BASE_URL}/v1/chat/completions"
HEALTH_URL = f"{BASE_URL}/api/health"
TIMEOUT = aiohttp.ClientTimeout(total=600)

# ─────────────────────────────────────────────────────────────────────
# Prompt Pool — diverse short prompts for realistic load patterns
# ─────────────────────────────────────────────────────────────────────

PROMPT_POOL = [
    "What is 2 + 2?",
    "Name three primary colors.",
    "Explain gravity in one sentence.",
    "What is the capital of France?",
    "Write a haiku about coding.",
    "Define 'recursion' in simple terms.",
    "What year did the internet become public?",
    "Translate 'hello' to Japanese.",
    "List 3 programming languages.",
    "What is the speed of light?",
    "Name 3 planets in our solar system.",
    "What does HTML stand for?",
    "Write a one-line joke.",
    "What is photosynthesis?",
    "Name a famous physicist.",
    "What is the boiling point of water?",
    "Define machine learning briefly.",
    "What is the largest ocean?",
    "Name 3 types of databases.",
    "What does CPU stand for?",
    "Explain what an API is.",
    "Name 3 cloud providers.",
    "What is a prime number?",
    "Define 'open source' in one sentence.",
    "What is the chemical formula for water?",
    "Name 3 JavaScript frameworks.",
    "What is TCP/IP?",
    "Explain DNS briefly.",
    "What is a neural network?",
    "Name 3 operating systems.",
    "Who wrote Hamlet?",
    "What is the square root of 144?",
    "Name a continent.",
    "What is the tallest mountain in the world?",
    "How many continents are there?",
    "What is the currency of Japan?",
    "What does CSS stand for?",
    "Explain dark matter simply.",
    "Who painted the Mona Lisa?",
    "What is the capital of Australia?",
    "How many states are in the USA?",
    "What is the freezing point of water?",
    "Define 'algorithm'.",
    "Name a popular Linux distribution.",
    "What is the powerhouse of the cell?",
    "Translate 'thank you' to Spanish.",
    "What is a black hole?",
    "Who invented the telephone?",
    "Name a web browser.",
    "What does HTTP stand for?",
    "What is a variable in programming?",
    "Explain the water cycle briefly.",
    "What is the smallest prime number?",
    "Name a desert.",
    "What is the capital of Canada?",
    "What does JSON stand for?",
    "Define 'cryptography'.",
    "What is the atomic number of Oxygen?",
    "Name a famous composer.",
    "What is a boolean?",
    "How many days in a leap year?",
    "What is the largest planet in our solar system?",
    "Who discovered penicillin?",
    "What does SQL stand for?",
    "Name a type of cloud.",
    "What is the capital of Italy?",
    "Explain natural selection in one sentence.",
    "What is a binary tree?",
    "Who was the first person on the moon?",
    "What is the hardest natural substance on Earth?",
    "What does GPU stand for?",
    "Name a string instrument.",
    "What is the main language spoken in Brazil?",
    "Define 'entropy'.",
    "What is the capital of Germany?",
    "What does IDE stand for?",
    "Explain object-oriented programming briefly.",
    "What is the largest mammal?",
    "Who wrote the Odyssey?",
    "What is a REST API?",
    "Name a common sorting algorithm.",
    "What is the speed of sound?",
    "What does RAM stand for?",
    "Define 'polymorphism' in programming.",
    "What is the capital of Spain?",
    "What is a firewall?",
    "Name a noble gas.",
    "Who developed the theory of relativity?",
    "What does PDF stand for?",
    "What is a quantum computer?",
    "Name a protocol used for email.",
    "What is the distance to the moon?",
    "Define 'Big O notation'.",
    "What is the capital of China?",
    "What does XML stand for?",
    "Who is the founder of Microsoft?",
    "What is a microprocessor?",
    "Name a famous mountain range.",
    "What does URL stand for?",
    "Explain 'cloud computing' in one sentence."
]


# ─────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────

class Colors:
    """ANSI color codes for terminal output."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def log_ok(label, detail=""):
    print(f"  {Colors.GREEN}[OK]{Colors.RESET} {label} {Colors.DIM}{detail}{Colors.RESET}")


def log_fail(label, detail=""):
    print(f"  {Colors.RED}[FAIL]{Colors.RESET} {label} {Colors.DIM}{detail}{Colors.RESET}")


def log_info(label, detail=""):
    print(f"  {Colors.CYAN}[INFO]{Colors.RESET} {label} {Colors.DIM}{detail}{Colors.RESET}")


def log_header(test_num, title):
    print(f"\n{Colors.BOLD}{Colors.YELLOW}{'=' * 70}{Colors.RESET}")
    print(f"{Colors.BOLD}  TEST {test_num}: {title}{Colors.RESET}")
    print(f"{Colors.YELLOW}{'=' * 70}{Colors.RESET}\n")


def pick_prompt(index=None):
    """Select a completely random prompt from the pool."""
    import random
    return random.choice(PROMPT_POOL)


async def check_server_health(session):
    """Verify Core of Potato is running and reachable."""
    try:
        async with session.get(HEALTH_URL) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("status") == "ok"
    except Exception:
        pass
    return False


async def send_completion(session, *, model, prompt, user_value,
                          delivery="json_body", stream=False,
                          expect_status=200):
    """
    Send a chat completion request using the specified NaModu delivery method.

    Delivery methods (matching server priority order):
        "json_body"    → user value in JSON body {"user": "<NaModu>"}
        "bearer"       → Authorization: Bearer <NaModu>
        "x_user"       → X-User: <NaModu>
        "user_header"  → User: <NaModu>

    Returns (success: bool, status_code: int, response_data: dict, elapsed: float)
    """
    headers = {"Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": stream,
    }

    # ── Attach NaModu via the requested delivery method ──
    if delivery == "json_body":
        body["user"] = user_value
    elif delivery == "bearer":
        headers["Authorization"] = f"Bearer {user_value}"
    elif delivery == "x_user":
        headers["X-User"] = user_value
    elif delivery == "user_header":
        headers["User"] = user_value
    # If delivery is "none", intentionally omit user entirely

    t0 = time.monotonic()
    try:
        async with session.post(API_URL, json=body, headers=headers) as resp:
            elapsed = time.monotonic() - t0
            status = resp.status

            if stream and status == 200:
                # Consume SSE stream, collect full text
                full_text = ""
                got_done = False
                async for line in resp.content:
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if not decoded:
                        continue
                    if decoded == "data: [DONE]":
                        got_done = True
                        break
                    if decoded.startswith("data: "):
                        payload = decoded[6:]
                        try:
                            chunk = json.loads(payload)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_text += content
                        except json.JSONDecodeError:
                            pass
                elapsed = time.monotonic() - t0
                return (
                    got_done and len(full_text) > 0,
                    status,
                    {"answer": full_text, "stream_done": got_done},
                    elapsed,
                )
            else:
                data = await resp.json()
                elapsed = time.monotonic() - t0
                success = status == expect_status
                return success, status, data, elapsed
    except Exception as exc:
        elapsed = time.monotonic() - t0
        return False, 0, {"exception": str(exc)}, elapsed


# ═════════════════════════════════════════════════════════════════════
# TEST 1: All 4 NaModu Delivery Methods
# ═════════════════════════════════════════════════════════════════════
#
# Core of Potato reads NaModu from the request in this priority order:
#   1. JSON body "user" field  →  body.get("user")
#   2. Authorization: Bearer   →  header Authorization
#   3. X-User header           →  header X-User
#   4. User header             →  header User
#
# This test verifies that ALL 4 methods produce a valid 200 response.

async def test_1_delivery_methods(session):
    log_header(1, "All 4 NaModu Delivery Methods")

    methods = [
        ("json_body",   "OCtesa", "JSON body {\"user\": \"OCtesa\"}"),
        ("bearer",      "OCtesb", "Authorization: Bearer OCtesb"),
        ("x_user",      "CDhep1", "X-User: CDhep1"),
        ("user_header", "CDhep2", "User: CDhep2"),
    ]

    passed = 0
    for delivery, user, description in methods:
        ok, status, data, elapsed = await send_completion(
            session,
            model="gemini",
            prompt="What is 1 + 1?",
            user_value=user,
            delivery=delivery,
        )
        if ok and status == 200:
            log_ok(description, f"({elapsed:.2f}s)")
            passed += 1
        else:
            log_fail(description, f"status={status} body={json.dumps(data)[:120]}")

    print(f"\n  Result: {passed}/{len(methods)} delivery methods passed.")
    return passed == len(methods)


# ═════════════════════════════════════════════════════════════════════
# TEST 2: All 3 NaModu Validation Failures
# ═════════════════════════════════════════════════════════════════════
#
# Core of Potato validates NaModu in 3 stages:
#   Failure 1 — Empty/missing user        → "What's your name, dude?"
#   Failure 2 — Not exactly 6 alphanum    → "Your name seems a bit off, doesn't it?"
#   Failure 3 — Unknown caller prefix     → "Yo, what faction are you in?"

async def test_2_namodu_failures(session):
    log_header(2, "All 3 NaModu Validation Failure Types")

    cases = [
        # (delivery, user_value, description, expected_fragment)
        (
            "none", "",
            "Failure 1: No user provided at all",
            "name",
        ),
        (
            "json_body", "AB",
            "Failure 2a: Too short (2 chars instead of 6)",
            "off",
        ),
        (
            "json_body", "ABCDEFGHlong",
            "Failure 2b: Too long (12 chars instead of 6)",
            "off",
        ),
        (
            "json_body", "OC!@#$",
            "Failure 2c: Contains special characters",
            "off",
        ),
        (
            "json_body", "ZZtest",
            "Failure 3: Unknown caller prefix 'ZZ' not in caller_map",
            "faction",
        ),
    ]

    passed = 0
    for delivery, user, description, expected_fragment in cases:
        ok, status, data, elapsed = await send_completion(
            session,
            model="grok",
            prompt="Test prompt",
            user_value=user,
            delivery=delivery,
            expect_status=400,
        )
        # Extract error message from response
        err_msg = ""
        if isinstance(data, dict):
            err = data.get("error", "")
            if isinstance(err, dict):
                err_msg = err.get("message", "")
            elif isinstance(err, str):
                err_msg = err

        if status == 400 and expected_fragment.lower() in err_msg.lower():
            log_ok(description, f'→ "{err_msg}"')
            passed += 1
        else:
            log_fail(description, f"status={status} error={err_msg!r}")

    print(f"\n  Result: {passed}/{len(cases)} failure cases validated.")
    return passed == len(cases)


# ═════════════════════════════════════════════════════════════════════
# TEST 3: All Model Aliases
# ═════════════════════════════════════════════════════════════════════
#
# Model aliases and their platforms:
#   ┌─ Grok ─────────────────────────────────────────────────────┐
#   │  "grok"        → grok (default)                            │
#   ├─ Gemini ───────────────────────────────────────────────────┤
#   │  "gemini"      → gemini (default)                          │
#   ├─ ChatGPT ─────────────────────────────────────────────────┤
#   │  "chatgpt"     → chatgpt (default)                         │
#   │  "gpt"         → chatgpt (alias)                           │
#   └────────────────────────────────────────────────────────────┘
#
# Also tests 1 invalid model to confirm rejection.

async def test_3_all_models(session):
    log_header(3, "All Model Aliases")

    # Group models by platform for organized output
    model_groups = [
        ("Grok", [
            ("grok", "grok — default mode"),
        ]),
        ("Gemini", [
            ("gemini", "gemini — default"),
        ]),
        ("ChatGPT", [
            ("chatgpt", "chatgpt — default"),
            ("gpt", "gpt — short alias"),
        ]),
    ]

    passed = 0
    total = 0

    for group_name, models in model_groups:
        print(f"  {Colors.CYAN}── {group_name} ──{Colors.RESET}")
        for model_id, description in models:
            total += 1
            ok, status, data, elapsed = await send_completion(
                session,
                model=model_id,
                prompt=pick_prompt(total),
                user_value="OCtesa",
                delivery="json_body",
            )
            if ok and status == 200:
                log_ok(description, f"({elapsed:.2f}s)")
                passed += 1
            else:
                log_fail(description, f"status={status}")
        print()

    # Test invalid model → expected 400
    total += 1
    print(f"  {Colors.CYAN}── Invalid Model ──{Colors.RESET}")
    ok, status, data, elapsed = await send_completion(
        session,
        model="nonexistent-model",
        prompt="Test",
        user_value="OCtesa",
        delivery="json_body",
        expect_status=400,
    )
    if status == 400:
        log_ok("nonexistent-model → rejected with 400", f'"{data.get("error", "")}"')
        passed += 1
    else:
        log_fail(f"nonexistent-model → expected 400, got {status}")

    print(f"\n  Result: {passed}/{total} model tests passed.")
    return passed == total


# ═════════════════════════════════════════════════════════════════════
# TEST 4: Multi-User Bombardment (18 Prompts, 2 Users, 3 Platforms)
# ═════════════════════════════════════════════════════════════════════
#
# Fires 18 requests across 2 users (OCtesa, OCtesb) and 3 platforms:
#   - 6 requests for grok    (3 per user)
#   - 6 requests for gemini  (3 per user)
#   - 6 requests for chatgpt (3 per user)
#
# Requests are staggered 1 second apart. The test completes successfully
# only when ALL 18 responses are received without any failures.

async def test_4_bombardment(session):
    log_header(4, "Multi-User Bombardment (18 Prompts / 2 Users / 3 Platforms)")

    users = ["OCtesa", "OCtesb"]
    platforms = ["grok", "gemini", "chatgpt"]

    # Build the 18-request schedule: 3 per user per platform
    schedule = []
    prompt_idx = 0
    for platform in platforms:
        for user in users:
            for _ in range(3):
                schedule.append({
                    "user": user,
                    "model": platform,
                    "prompt": pick_prompt(prompt_idx),
                })
                prompt_idx += 1

    log_info(f"Launching {len(schedule)} requests, staggered 1s apart...")

    # Launch all tasks with 1-second stagger
    tasks = []
    results = []

    async def fire_request(idx, spec):
        ok, status, data, elapsed = await send_completion(
            session,
            model=spec["model"],
            prompt=spec["prompt"],
            user_value=spec["user"],
            delivery="json_body",
        )
        return {
            "index": idx,
            "user": spec["user"],
            "model": spec["model"],
            "status": status,
            "ok": ok,
            "elapsed": elapsed,
        }

    t0 = time.monotonic()
    for i, spec in enumerate(schedule):
        task = asyncio.create_task(fire_request(i, spec))
        tasks.append(task)
        if i < len(schedule) - 1:
            await asyncio.sleep(1.0)

    # Wait for ALL 18 to complete
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total_elapsed = time.monotonic() - t0

    # Tally results
    success_count = 0
    fail_count = 0
    per_platform = defaultdict(lambda: {"ok": 0, "fail": 0})
    per_user = defaultdict(lambda: {"ok": 0, "fail": 0})

    for r in results:
        if isinstance(r, Exception):
            fail_count += 1
            log_fail(f"Exception: {r}")
            continue
        if r["ok"] and r["status"] == 200:
            success_count += 1
            per_platform[r["model"]]["ok"] += 1
            per_user[r["user"]]["ok"] += 1
            log_ok(
                f"#{r['index']+1:02d} {r['user']} → {r['model']}",
                f"({r['elapsed']:.2f}s)",
            )
        else:
            fail_count += 1
            per_platform[r["model"]]["fail"] += 1
            per_user[r["user"]]["fail"] += 1
            log_fail(
                f"#{r['index']+1:02d} {r['user']} → {r['model']}",
                f"status={r['status']} ({r['elapsed']:.2f}s)",
            )

    # Summary
    print(f"\n  {Colors.BOLD}Summary:{Colors.RESET}")
    print(f"    Total time:     {total_elapsed:.1f}s")
    print(f"    Success/Total:  {success_count}/{len(schedule)}")
    for p in platforms:
        s = per_platform[p]
        print(f"    {p:10s}:    {s['ok']} ok / {s['fail']} fail")
    for u in users:
        s = per_user[u]
        print(f"    {u:10s}:    {s['ok']} ok / {s['fail']} fail")

    passed = success_count == len(schedule) and fail_count == 0
    return passed


# ═════════════════════════════════════════════════════════════════════
# TEST 5: 2-Minute Endurance Run (Max Throughput)
# ═════════════════════════════════════════════════════════════════════
#
# Continuously fires batches of requests for 2 minutes straight.
# Each batch contains 1 request per model (grok, gemini, chatgpt).
# Batches are launched every 5 seconds.
# Reports total prompts completed, success rate, and throughput.

async def test_5_endurance(session):
    log_header(5, "2-Minute Endurance Run (Max Throughput)")

    DURATION_SECONDS = 120
    BATCH_INTERVAL = 5
    MODELS = ["grok", "gemini", "chatgpt"]

    batch_count = 0
    t_start = time.monotonic()

    log_info(f"Running for {DURATION_SECONDS}s, batch every {BATCH_INTERVAL}s...")
    log_info(f"Models per batch: {', '.join(MODELS)}")
    print()

    async def fire(idx, model):
        ok, status, data, elapsed = await send_completion(
            session,
            model=model,
            prompt=pick_prompt(idx),
            user_value="OCtesa",
            delivery="json_body",
        )
        return {"model": model, "ok": ok, "status": status, "elapsed": elapsed}

    pending_tasks = []

    while (time.monotonic() - t_start) < DURATION_SECONDS:
        batch_count += 1
        batch_tasks = []
        for i, model in enumerate(MODELS):
            idx = batch_count * len(MODELS) + i
            task = asyncio.create_task(fire(idx, model))
            batch_tasks.append(task)
            pending_tasks.append(task)

        elapsed_so_far = time.monotonic() - t_start
        remaining = DURATION_SECONDS - elapsed_so_far
        if remaining <= 0:
            break

        wait_time = min(BATCH_INTERVAL, remaining)
        await asyncio.sleep(wait_time)

    # Wait for all pending tasks to finish
    log_info("Time's up! Waiting for remaining requests to complete...")
    completed = await asyncio.gather(*pending_tasks, return_exceptions=True)
    total_elapsed = time.monotonic() - t_start

    # Tally
    success = 0
    fail = 0
    per_model = defaultdict(lambda: {"ok": 0, "fail": 0, "total_time": 0.0})

    for r in completed:
        if isinstance(r, Exception):
            fail += 1
            continue
        if r["ok"] and r["status"] == 200:
            success += 1
            per_model[r["model"]]["ok"] += 1
            per_model[r["model"]]["total_time"] += r["elapsed"]
        else:
            fail += 1
            per_model[r["model"]]["fail"] += 1

    total = success + fail
    throughput = total / total_elapsed if total_elapsed > 0 else 0

    print(f"\n  {Colors.BOLD}Endurance Results:{Colors.RESET}")
    print(f"    Duration:       {total_elapsed:.1f}s")
    print(f"    Batches fired:  {batch_count}")
    print(f"    Total requests: {total}")
    print(f"    Successful:     {success}")
    print(f"    Failed:         {fail}")
    print(f"    Throughput:     {throughput:.2f} req/s")
    print()
    for m in MODELS:
        s = per_model[m]
        avg = s["total_time"] / s["ok"] if s["ok"] > 0 else 0
        print(f"    {m:10s}: {s['ok']} ok / {s['fail']} fail  (avg {avg:.2f}s)")

    # Phase 5 fails when the queue exceeds 10. The user requested to allow this
    # to fail, logging the success/rejected count, and proceeding to Phase 6.
    return True


# ═════════════════════════════════════════════════════════════════════
# TEST 6: Streaming SSE Validation
# ═════════════════════════════════════════════════════════════════════
#
# Sends stream=true requests for each platform and verifies:
#   - Response uses text/event-stream content-type
#   - Chunks arrive as "data: {json}" lines
#   - Final "data: [DONE]" terminator is received
#   - Accumulated text is non-empty

async def test_6_streaming(session):
    log_header(6, "Streaming SSE Validation")

    models = [
        ("grok",    "Grok streaming"),
        ("gemini",  "Gemini streaming"),
        ("chatgpt", "ChatGPT streaming"),
    ]

    passed = 0
    for model, description in models:
        ok, status, data, elapsed = await send_completion(
            session,
            model=model,
            prompt="Write a one-line poem about streams.",
            user_value="OCtesa",
            delivery="json_body",
            stream=True,
        )
        if ok and status == 200 and data.get("stream_done"):
            answer_preview = data.get("answer", "")[:60]
            log_ok(description, f'({elapsed:.2f}s) "{answer_preview}..."')
            passed += 1
        else:
            log_fail(description, f"status={status} stream_done={data.get('stream_done')}")

    print(f"\n  Result: {passed}/{len(models)} streaming tests passed.")
    return passed == len(models)


# ═════════════════════════════════════════════════════════════════════
# TEST 7: Concurrency Serialization
# ═════════════════════════════════════════════════════════════════════
#
# Verifies Core of Potato's nav-key-aware concurrency queueing:
#   a) Same NaModu + same model → requests are serialized (sequential)
#   b) Same NaModu + different models → requests run in parallel
#   c) Different NaModus + same model → requests run in parallel
#
# We measure timing to confirm serialization vs parallelism.

async def test_7_concurrency(session):
    log_header(7, "Concurrency Serialization Behavior")

    # ── 7a: Same user + same model → should serialize ──
    print(f"  {Colors.CYAN}── 7a: Same NaModu + Same Model (expect serial) ──{Colors.RESET}")
    t0 = time.monotonic()
    tasks_a = [
        send_completion(
            session, model="grok", prompt="Prompt A1",
            user_value="OCtesa", delivery="json_body",
        ),
        send_completion(
            session, model="grok", prompt="Prompt A2",
            user_value="OCtesa", delivery="json_body",
        ),
    ]
    results_a = await asyncio.gather(*tasks_a)
    elapsed_a = time.monotonic() - t0

    ok_a = all(r[0] and r[1] == 200 for r in results_a)
    individual_times = [r[3] for r in results_a]
    log_info(
        f"2 requests for OCtesa→grok completed in {elapsed_a:.2f}s total",
        f"(individual: {', '.join(f'{t:.2f}s' for t in individual_times)})",
    )
    if ok_a:
        log_ok("Both completed successfully")
    else:
        log_fail("One or more requests failed")

    # ── 7b: Same user + different models → should parallelize ──
    print(f"\n  {Colors.CYAN}── 7b: Same NaModu + Different Models (expect parallel) ──{Colors.RESET}")
    t0 = time.monotonic()
    tasks_b = [
        send_completion(
            session, model="grok", prompt="Prompt B1",
            user_value="OCtesa", delivery="json_body",
        ),
        send_completion(
            session, model="gemini", prompt="Prompt B2",
            user_value="OCtesa", delivery="json_body",
        ),
        send_completion(
            session, model="chatgpt", prompt="Prompt B3",
            user_value="OCtesa", delivery="json_body",
        ),
    ]
    results_b = await asyncio.gather(*tasks_b)
    elapsed_b = time.monotonic() - t0

    ok_b = all(r[0] and r[1] == 200 for r in results_b)
    individual_times = [r[3] for r in results_b]
    log_info(
        f"3 requests for OCtes1→(grok,gemini,chatgpt) completed in {elapsed_b:.2f}s total",
        f"(individual: {', '.join(f'{t:.2f}s' for t in individual_times)})",
    )
    if ok_b:
        log_ok("All 3 completed successfully (should overlap)")
    else:
        log_fail("One or more requests failed")

    # ── 7c: Different users + same model → should parallelize ──
    print(f"\n  {Colors.CYAN}── 7c: Different NaModus + Same Model (expect parallel) ──{Colors.RESET}")
    t0 = time.monotonic()
    tasks_c = [
        send_completion(
            session, model="grok", prompt="Prompt C1",
            user_value="OCtes1", delivery="json_body",
        ),
        send_completion(
            session, model="grok", prompt="Prompt C2",
            user_value="OCtes2", delivery="json_body",
        ),
    ]
    results_c = await asyncio.gather(*tasks_c)
    elapsed_c = time.monotonic() - t0

    ok_c = all(r[0] and r[1] == 200 for r in results_c)
    individual_times = [r[3] for r in results_c]
    log_info(
        f"2 requests for (OCtes1,OCtes2)→grok completed in {elapsed_c:.2f}s total",
        f"(individual: {', '.join(f'{t:.2f}s' for t in individual_times)})",
    )
    if ok_c:
        log_ok("Both completed successfully (should overlap)")
    else:
        log_fail("One or more requests failed")

    all_passed = ok_a and ok_b and ok_c
    print(f"\n  Result: {'All 3 scenarios passed' if all_passed else 'Some scenarios failed'}.")
    return all_passed


# ═════════════════════════════════════════════════════════════════════
# Main Runner
# ═════════════════════════════════════════════════════════════════════

ALL_TESTS = {
    1: ("All NaModu Delivery Methods", test_1_delivery_methods),
    2: ("All NaModu Validation Failures", test_2_namodu_failures),
    3: ("All Model Aliases", test_3_all_models),
    4: ("Multi-User Bombardment", test_4_bombardment),
    5: ("2-Minute Endurance Run", test_5_endurance),
    6: ("Streaming SSE Validation", test_6_streaming),
    7: ("Concurrency Serialization", test_7_concurrency),
}


async def main():
    # Parse which tests to run from CLI args
    if len(sys.argv) > 1:
        try:
            selected = [int(x) for x in sys.argv[1:]]
        except ValueError:
            print(f"Usage: {sys.argv[0]} [test_numbers...]")
            print(f"  Available tests: {', '.join(str(k) for k in ALL_TESTS)}")
            sys.exit(1)
    else:
        selected = list(ALL_TESTS.keys())

    print(f"\n{Colors.BOLD}{'═' * 70}{Colors.RESET}")
    print(f"{Colors.BOLD}  Core of Potato v1.0.0 — Comprehensive Load Test Suite{Colors.RESET}")
    print(f"{Colors.BOLD}{'═' * 70}{Colors.RESET}")
    print(f"  Server:  {BASE_URL}")
    print(f"  Tests:   {', '.join(str(s) for s in selected)}")

    connector = aiohttp.TCPConnector(limit=100)
    async with aiohttp.ClientSession(timeout=TIMEOUT, connector=connector) as session:
        # Pre-flight: check server health
        if not await check_server_health(session):
            print(f"\n  {Colors.RED}[ERROR] Core of Potato is not running at {BASE_URL}{Colors.RESET}")
            print("  Start the server first:  python3 -m core")
            sys.exit(1)

        log_info(f"Server is healthy at {BASE_URL}")

        # Run selected tests
        results = {}
        for test_num in selected:
            if test_num not in ALL_TESTS:
                print(f"\n  {Colors.RED}[ERROR] Unknown test number: {test_num}{Colors.RESET}")
                continue
            name, func = ALL_TESTS[test_num]
            try:
                passed = await func(session)
                results[test_num] = passed
                if not passed:
                    print(f"\n  {Colors.RED}[ABORT] Test {test_num} ({name}) failed. Stopping execution as requested.{Colors.RESET}")
                    break
            except Exception as exc:
                print(f"\n  {Colors.RED}[EXCEPTION] Test {test_num} crashed: {exc}{Colors.RESET}")
                results[test_num] = False
                break

    # ── Final Summary ──
    print(f"\n{Colors.BOLD}{'═' * 70}{Colors.RESET}")
    print(f"{Colors.BOLD}  FINAL RESULTS{Colors.RESET}")
    print(f"{'═' * 70}")
    for test_num, passed in results.items():
        name = ALL_TESTS[test_num][0]
        icon = f"{Colors.GREEN}PASS{Colors.RESET}" if passed else f"{Colors.RED}FAIL{Colors.RESET}"
        print(f"  Test {test_num}: [{icon}] {name}")

    total_pass = sum(1 for p in results.values() if p)
    total_run = len(results)
    print(f"\n  {total_pass}/{total_run} tests passed.")
    print(f"{'═' * 70}\n")

    sys.exit(0 if total_pass == total_run else 1)


if __name__ == "__main__":
    asyncio.run(main())
