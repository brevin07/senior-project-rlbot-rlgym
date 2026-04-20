Brevin Tating  
btating@westmont.edu  
CS-195 Senior Seminar  
Mike Ryu

# RocketCoach

## Overview

RocketCoach is a replay-driven Rocket League coaching platform designed to help players move from vague self-review to concrete improvement. Instead of centering the project on custom AI opponents or PPO-trained agents, the current project focuses on parsing replay data, identifying mechanical weaknesses, surfacing event-based coaching feedback, tracking progress over time, and guiding players toward targeted practice.

## Motivation

Rocket League has a uniquely high skill ceiling because improvement depends on timing, positioning, decision making, recoveries, and mechanical consistency under pressure. Human coaching can be helpful, but it is expensive and not available on demand for most players. Existing tools are fragmented: players can watch replays, use workshop maps or training packs, and queue ranked games, but they still have to figure out for themselves what went wrong and what to practice next.

RocketCoach addresses that gap by turning replay data into structured feedback. The goal is not to build an artificial opponent that teaches the player directly, but to provide a reliable system that diagnoses mistakes, explains them in context, and supports a repeatable improvement loop.

## Problem Statement

Aspiring competitive Rocket League players often lack an accessible, consistent coaching workflow. They can save and review replays, but replay review is slow, subjective, and difficult to translate into action. A player may know they lost a game, but not whether the root cause was shadow defense, challenge timing, 50/50 control, aerial reads, or recoveries. Without a tool that highlights recurring weaknesses, stores results, and connects them to concrete next steps, players are forced to rely on guesswork.

## Proposed Solution

- Diagnosis: A Python replay-analysis backend parses `.replay` files into structured telemetry and computes mechanic-oriented signals, event markers, and weakness summaries.
- Explanation: A coaching layer converts those signals into readable feedback so a player can understand what happened and why it mattered in the match.
- Tracking: Replay summaries, mechanic grades, and session history are stored so players can review improvement over time instead of treating every replay in isolation.
- Guided Practice: The dashboard recommends targeted areas to practice based on replay evidence and can hand the user off to focused drills or training workflows without making custom AI opponents the center of the system.

## Specifications

- Replay Analysis: A Python interface uses the rrrocket utility to extract replay telemetry, calculate derived metrics, identify mechanic-specific events, and store replay summaries in SQL-backed persistence.
- Coaching Logic: Heuristic grading and event analysis flag specific weaknesses such as challenge timing, shadow defense, aerial defense, aerial offense, or 50/50 control and attach replay-backed explanations.
- Persistence Layer: User accounts, profiles, replay sessions, mechanic summaries, and historical progress data are stored so the system can compare performance across multiple replays.
- User Dashboard: A React + TypeScript dashboard provides authentication, replay upload, replay review, event-based coaching, progress tracking, and installer/training workflow surfaces.
- Guided Practice Integration: The system maps weak mechanics to recommended practice paths and difficulty tiers. This project no longer depends on training custom PPO agents or on AI-opponent development as its core deliverable.

## Justifications

- Novelty: Many tools cover only one step of the workflow, such as replay viewing, stat lookup, or isolated training content. RocketCoach brings together replay parsing, mechanic grading, coaching feedback, persistence, and practice recommendations in one continuous loop.
- Feasibility: The project already contains working replay ingestion, event grading, persistence, dashboard integration, and launcher workflows. The current scope is more realistic than the earlier custom-bot plan because it focuses on integrating and validating coaching features that are already active in the repository.
- Cost: The project relies primarily on open-source tooling such as Python, React, SQLite, RLBot ecosystem tooling, and replay utilities. Optional AI-generated explanation features may use an API, but the core coaching pipeline does not depend on training or shipping custom machine-learned opponents.

## Milestones

### Mission Statement

Engineer a replay-driven coaching system that analyzes Rocket League gameplay, identifies player weaknesses, explains mistakes in context, and supports measurable improvement through history-aware feedback and guided practice.

### OKRs

#### Milestone 1: Alpha Release (Diagnosis Phase)

Objective: Provide users with an immediate, data-backed view of their fundamental mechanical weaknesses using replay analysis and deterministic grading.

- KR 1: System successfully parses and extracts telemetry from valid standard `.replay` files into a queryable Pandas structure.
- KR 2: Develop an algorithm that flags at least 3 specific player weaknesses based on replay-derived statistical thresholds and mechanic events.
- KR 3: The 3D replay visualizer renders player positions at greater than 30 FPS within the application and can pause on identified mistake timestamps without crashing.
- KR 4: SQL persistence successfully stores and queries replay sessions, user profile data, and replay-derived mechanic summaries.

#### Milestone 2: Beta Release (Coaching Workflow Phase)

Objective: Turn replay diagnostics into a usable coaching product that players can navigate end to end through the dashboard.

- KR 1: Users can upload a replay and review mechanic grades, event markers, and replay-backed coaching feedback in a unified dashboard flow.
- KR 2: The system recommends at least 3 actionable focus areas or practice targets based on replay results rather than generic advice.
- KR 3: Coaching text and replay review remain usable even when explanation generation or background processing is still in progress.

#### Milestone 3: Release Candidate (Growth Phase)

Objective: Deliver a reliable upload-to-improvement loop that helps users recognize habits, track change over time, and return to the product.

- KR 1: The system processes a standard replay and renders the relevant dashboard experience in under 10 seconds on the target setup.
- KR 2: In a user study of 3 or more Rocket League players, every participant identifies at least one previously unnoticed weakness or recurring game-losing habit.
- KR 3: The system correlates data from multiple replays to generate progress views showing trend movement in specific mechanics across upload history.

## Grading Criteria

For non-binary tasks, grading criteria will be used to distinguish partial from strong attainment. Binary tasks should still be judged as pass/fail.

### M1 KR2: Weakness Detection Accuracy

- A: Flags weaknesses with greater than 90% agreement against manual human review.
- B: Greater than 80% agreement.
- C: Greater than 70% agreement with occasional false positives.
- D: Less than 50% agreement and inconsistent usefulness.
- F: Fails to flag obvious recurring weaknesses.

### M2 KR1: Unified Coaching Workflow

- A: User can upload, open, review replay markers, read coaching, and navigate results with no major blockers.
- B: Core replay and coaching workflow works with minor friction.
- C: Workflow works, but important steps are manual or confusing.
- D: Workflow is unstable or regularly breaks the review experience.
- F: No usable end-to-end replay coaching flow exists.

### M2 KR2: Actionable Practice Recommendation Quality

- A: Recommendations are clearly personalized, prioritized, and directly tied to replay evidence.
- B: Recommendations are personalized and usually helpful.
- C: Recommendations are present but somewhat generic.
- D: Recommendations are weakly connected to replay evidence.
- F: No meaningful practice recommendations are generated.

### M3 KR1: Replay-to-Dashboard Latency

- A: Full analysis and render in under 5 seconds.
- B: Full analysis and render in under 10 seconds.
- C: Full analysis and render in under 30 seconds.
- D: Full analysis and render in over 1 minute.
- F: System times out or crashes.

### M3 KR3: Historical Progress Tracking

- A: Interactive charts show history and meaningful improvement trends across mechanics.
- B: Static charts or strong summary views show improvement over time.
- C: Simple table compares recent and prior replay results.
- D: Raw list of past stats only.
- F: No historical tracking.

## Credits / Acknowledgements

Dominic Tating, Dan Shank, Mike Ryu
