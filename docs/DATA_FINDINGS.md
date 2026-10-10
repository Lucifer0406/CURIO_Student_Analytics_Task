# Data findings - Curio analytics export

Inspection of the MongoDB JSON export (17 collections) carried out on 2026-10-10, before building the
dashboard. The inspection read field names, types, counts and ID relationships only; no personal values
were printed or copied. The export itself is **not** in this repository.

## What the data supports

| Architecture component | Collection(s) | Usable? | Notes |
|---|---|---|---|
| Learning time, streak, consistency | `engagementSessions`, `toolusages` | Yes | `durationSec` per session; no subject field |
| Overall accuracy, quiz count, badges | `quizattempts.answers[].isCorrect` | Yes | Summary fields are unreliable (see below) |
| Subject / topic / difficulty accuracy | `assessmentattempts` → `assessments.questionSnapshots` | Yes, for 7 students | 1127/1127 answers join to a question snapshot |
| Time per question | `assessmentattempts.answers[].timeTakenMs` | Assessments only | Practice quizzes don't record it |
| Progress over time | timestamps | Limited | 461 of 500 practice attempts fall in Feb 2026 |
| Topic mastery | derived | Prototype formula | `studentmasteries` is empty |
| AI diagnostics | `aianalysishistories.insights` | Display only | Stored text; not recomputed |

## Data-quality issues and how the app handles them

| Issue | Evidence | Handling |
|---|---|---|
| `quizattempts` summary fields contradict the answers | `correctAnswers` ≠ count of correct answers in 433/500; `score > totalMarks` in 411; `totalQuestions = 0` with 10 answers | Accuracy is rebuilt from `answers[].isCorrect` |
| No subject, quiz ID, tags or difficulty on practice answers | `tags` empty in all 4,586 answers; `questionId` joins the question bank 8 times out of 351 | Practice answers are labelled "Unmapped" in topic/subject views |
| Practice quiz duration missing | `startedAt == completedAt` in 452/500 | No per-quiz duration metric |
| Blank answers in assessments | Missing `userAnswer` 576 times = exactly the sum of `result.unattemptedCount` | Treated as blank (wrong) |
| Missing `userAnswer` in practice | 795 such answers are still marked correct | Treated as unknown, not blank |
| Ungraded assessment answers | 9 answers with `evaluationStatus = PENDING` | Excluded from accuracy |
| Duplicate session sources | `topicinteractions` shares 498/500 `sessionId`s with `engagementSessions` | `topicinteractions` is not loaded |
| Tool/learning overlap | 97 of 607 tool seconds overlap a learning session | Small; documented as a limitation |
| Messy subject labels | "12th Physics", "physics", "11 th phy", "chem", "maths testing 3", … | `normalize_subject()`; unknown → "Unmapped" |
| Pass threshold not in data | `passingScore` is 0 (83) or 15 (4); every attempt `PROMOTED` | Diagram's 70% used as the reference line |
| Possible test account | one user has 336 practice attempts | Not used for the demo |
| Voice sessions mostly orphaned | 99 of 105 `userId`s are not in `users` | Not loaded |

## Coverage: why the demo uses a synthetic student

No real student has quiz, assessment and engagement data at the same time. The best quiz + engagement
profile has 11 quizzes, 136 sessions and 0 assessments; students with assessments have almost no
engagement data. Combining records from different students would produce a profile that doesn't exist,
so the public demo uses one generated student (`scripts/generate_synthetic.py`) that follows the same
schema. The same code runs on the real export locally.

## Privacy

`users.json` contains names, emails, phone numbers, dates of birth, password hashes, session tokens and
live OTP codes. The loader never reads `users.json` or `conversationhistories.json`, and `.gitignore`
blocks every `.json`/`.zip` file outside `data/synthetic/`. **Recommendation for the platform team:**
exports for analytics work should exclude credential fields (`passwordHash`, `currentToken`, `otp`).
