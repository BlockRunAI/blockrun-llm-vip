# Real-Person Video — the supported flow

**Yes, real people are supported.** A specific, real human can appear consistently
across as many Seedance videos as you want. This document is the canonical end-to-end
flow for doing that with `blockrun-llm-vip`, plus the decision tree, state machine, and
error states.

It exists because the capability is easy to miss: if you try to upload a real-person
photo directly to a generic image-to-video call (or to Sora), it gets **rejected** — and
it's natural to conclude "the API doesn't support real people." It does. Real-person
video just goes through a different, consent-based door: **RealFace enrollment**, not a
raw face upload.

---

## TL;DR

```python
from blockrun_llm_vip import RealFace, Video

rf = RealFace()
started = rf.init("Spokesperson — Q3 campaign")          # FREE
print("Open on the rights-holder's phone:", started["h5_link"])   # QR / mobile link

rf.wait_until_active(started["group_id"])                # after they nod + blink (~1 min)
asset = rf.enroll(                                       # PAID — $0.01 USDC, one-time
    name="Spokesperson — Q3 campaign",
    image_url="https://example.com/person.jpg",
    group_id=started["group_id"],
)

video = Video()
job = video.generate(
    "she smiles warmly and waves at the camera in soft studio light",
    model="bytedance/seedance-2.0",
    real_face_asset_id=asset["asset_id"],                # ta_xxxx — the real person
)
print(job["data"][0]["url"])                             # permanent MP4 of that person
```

That `ta_xxxx` is reusable forever — pay the per-clip cost each time, never re-enroll.

---

## Common misunderstanding → correction

| What people believe | What's actually true |
|---|---|
| "The API doesn't support real people, only virtual portraits." | Real people **are** supported via **RealFace**. Virtual Portrait is the *separate* path for AI-generated characters. |
| "blockrun doesn't allow real-person likeness." | It does — gated behind a lightweight **on-phone liveness check** (proof of consent), **not** KYC and **not** an offline rights-holder contract. |
| "I uploaded a face and it was rejected, so it's unsupported." | A **raw face upload** to Sora / generic image-to-video is blocked by design (anti-deepfake). The supported route is **enroll once via RealFace, then reference the `ta_xxxx`** — not a per-call face upload. |
| "Real-person needs a 10万/30万 rights package / offline contract first." | That's a **commercial** question, not a technical gate. The technical capability is **live today** at $0.01/enrollment. The only consent mechanism the API requires is the liveness check. |

---

## Two asset types — which door do you use?

Both produce a `ta_xxxx` asset that you pass as `real_face_asset_id` on Seedance
2.0 / 2.0-fast. The only difference is what the asset represents and whether consent
liveness is required.

```
                Is the subject a REAL, specific human?
                          │
            ┌─────────────┴─────────────┐
           YES                          NO  (AI character / mascot / avatar)
            │                            │
       ┌────▼─────┐                ┌─────▼──────────┐
       │ RealFace │                │ VirtualPortrait │
       └────┬─────┘                └─────┬──────────┘
   consent liveness (~1 min,        no liveness, single
   nod+blink on phone, NO KYC)      $0.01 x402 call
            │                            │
            └──────────────┬─────────────┘
                       ta_xxxx
                           │
                 real_face_asset_id on
              Seedance 2.0 / 2.0-fast video
```

| | `VirtualPortrait` | `RealFace` |
|---|---|---|
| Subject | AI-generated character | A real, specific person |
| Liveness check | None | Required (~1 min on the rights-holder's phone) |
| KYC / government ID | No | No |
| Upstream verification | None | Biometric match: enrolled photo ↔ live H5 face |
| Price | $0.01 USDC, one-time | $0.01 USDC, one-time |
| Compatible models | Seedance 2.0 / 2.0-fast | Seedance 2.0 / 2.0-fast |
| SDK class | `VirtualPortrait` / `AsyncVirtualPortrait` | `RealFace` / `AsyncRealFace` |

> **Why no raw face upload?** Sora 2 (and generic image-to-video) reject reference
> images containing recognizable human faces — a deliberate anti-deepfake guard. So the
> only consented real-person path is the enroll-once-then-reference model below. The
> SDK enforces the same shape: `real_face_asset_id` and `image_url` are **mutually
> exclusive**, and `real_face_asset_id` is only accepted on Seedance 2.0 / 2.0-fast.

---

## RealFace state machine

```
   ┌──────────────────────────── RealFace().init(name) ── FREE
   │                              returns { group_id, h5_link, expires_in_seconds: 120 }
   ▼
[ pending_validation ] ── rights-holder opens h5_link on their phone ──┐
   │   ▲                                                               │
   │   │  (120s H5 session expired?                                    │
   │   │   init(name, group_id=…) to refresh)                          │
   │   └───────────────────────────────────────────────────────────┐  │
   │                                                                │  │
   │   poll RealFace().status(group_id)  ── FREE (every 3–5s)       │  │
   │   or RealFace().wait_until_active(group_id)                    │  │
   ▼                                                                │  │
[ active / ready_to_finalize ] ◄────── nod + blink, 2–4s liveness ─┘◄─┘
   │
   │   RealFace().enroll(name, image_url, group_id) ── PAID $0.01 USDC (x402)
   │   upstream face-matches image_url against the live H5 face
   ▼
[ enrolled ]  →  asset["asset_id"] = "ta_xxxx"
   │
   ▼
Video().generate(prompt, model="bytedance/seedance-2.0",
                 real_face_asset_id="ta_xxxx")   ← reuse forever
```

| Step | SDK call | Cost | Notes |
|---|---|---|---|
| 1. Init | `rf.init(name)` | FREE | Returns `group_id` + `h5_link`. Rate-limited (10/hr/IP). H5 session lives 120s. |
| 2. Liveness | *(rights-holder, on phone)* | — | Scan `h5_link` as a QR or open on mobile. Nod + blink, 2–4s. No login, no ID upload. Camera-blocked fallback: record + upload a short video. Works on a laptop webcam too. |
| 3. Poll | `rf.status(group_id)` / `rf.wait_until_active(group_id)` | FREE | `pending_validation` → `active`. Poll every 3–5s. |
| 4. Enroll | `rf.enroll(name=, image_url=, group_id=)` | **$0.01 USDC** | Settles **only** after the face-match succeeds. Returns `ta_xxxx`. |
| 5. Generate | `Video().generate(..., real_face_asset_id=)` | per-clip | Reuse the `ta_xxxx` across unlimited clips. |
| —. List | `rf.list()` | FREE | All RealFace assets this wallet has enrolled. |

Whole sequence typically completes in **under 3 minutes** — mostly the person finding
their phone and tapping through the H5.

---

## Error / state reference

The single x402 transport handles the money: the free `init` / `status` / `list` calls
return `200` directly (nothing signed), and only `enroll` triggers the $0.01 settlement.

| Condition | HTTP | SDK surface | Did payment settle? |
|---|---|---|---|
| Group not yet `active` (liveness not done) | 425 | `RealFaceError` from `enroll()` | **No** |
| Face-match failed (photo ≠ live face) | 422 | `RealFaceError` from `enroll()` | **No** |
| Upload to inference partner failed | 502 | `RealFaceError` from `enroll()` | **No** |
| Bad request body / image URL / group id | 400 | `RealFaceError` | — (pre-payment) |
| Rate limit on `init` / `status` | 429 | `RealFaceError` | — |
| Group never reaches `active` in time | — | `RealFaceTimeout` from `wait_until_active()` | — |
| `image_url` **and** `real_face_asset_id` both set | (client) | `ValueError` from `Video.generate()` | — |
| `real_face_asset_id` on a non-Seedance-2.0 model | (client) | `ValueError` from `Video.generate()` | — |
| Enrolled and active | 200 | `enroll()` returns `{asset_id: "ta_…", settlement: {...}}` | **Yes** |

Import the exception types from the package root:

```python
from blockrun_llm_vip import RealFaceError, RealFaceTimeout
```

`enroll()` settlement is consent-safe: if the live face doesn't match the photo (422)
or the rights-holder hasn't finished the liveness check (425), **no USDC moves**.

---

## Async

Every class has an async twin with the same method names:

```python
from blockrun_llm_vip import AsyncRealFace, AsyncVideo

async with AsyncRealFace() as rf:
    started = await rf.init("Spokesperson")
    # ... share h5_link, then:
    await rf.wait_until_active(started["group_id"])
    asset = await rf.enroll(
        name="Spokesperson",
        image_url="https://example.com/person.jpg",
        group_id=started["group_id"],
    )

async with AsyncVideo() as video:
    job = await video.generate(
        "she waves at the camera",
        model="bytedance/seedance-2.0-fast",
        real_face_asset_id=asset["asset_id"],
    )
```

---

## AI character instead of a real person

If the subject is a synthetic character (mascot, avatar, virtual spokesperson), skip
the liveness step entirely — enroll a **Virtual Portrait** and use the identical
`ta_xxxx` → `real_face_asset_id` flow:

```python
from blockrun_llm_vip import VirtualPortrait

vp = VirtualPortrait()
asset = vp.enroll(name="Mascot", image_url="https://example.com/character.jpg")  # $0.01
# pass asset["asset_id"] as real_face_asset_id on Seedance 2.0 / 2.0-fast
```

---

## Gateway references

- RealFace API: `…/api-reference/realface.md` — endpoints, H5 walkthrough, privacy
- Virtual Portrait API: `…/api-reference/virtual-portrait.md`
- Video Generation API: `…/api-reference/video-generation.md` — models, pricing, polling
- RealFace Studio (no-code web flow): https://blockrun.ai/studio/realface
- Real-person video walkthrough: https://blockrun.ai/docs/video/real-person-ip
