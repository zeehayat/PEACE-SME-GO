# Chapter 12: HFC Fraud Detection and Approval Authority

## Purpose

HFC teaches deterministic scoring, background recalculation, audit trails, and role-based approvals.

## Theoretical Background

### Rule-Based Engines vs. ML Models
In fraud detection and risk scoring, systems use one of two main approaches:
1. **Deterministic Rule-Based Engines:** Apply strict, logical heuristics to evaluate input data (e.g., "If email already exists, add 20 points").
   - **Pros:** 100% transparent, predictable, easy to debug, and requires no training datasets.
   - **Cons:** Rigid; cannot easily detect novel fraud patterns that do not violate explicit rules.
2. **Machine Learning Classifiers:** Make probabilistic predictions based on feature sets learned from historical data.
   - **Pros:** Can detect complex, non-linear fraud signals.
   - **Cons:** Hard to explain (black-box problem), prone to data drift, and slower to execute.
   
This application utilizes a deterministic rule engine (v1) as its primary scorer, with optional hook points for ML scoring.

### Message Processing Guarantees
When background workers process jobs (such as recalculating HFC scores or sending approval notifications), three execution guarantees are possible:
- **At-Most-Once:** The job is pulled from the queue and immediately marked complete before execution. If the worker crashes mid-job, the task is lost.
- **At-Least-Once (Recommended):** The job remains in the queue (or in a processing state) until the worker explicitly acknowledges completion. If the worker crashes, the job is re-run. This requires writing **Idempotent** tasks (tasks that can run multiple times safely without duplicate side-effects).
- **Exactly-Once:** Achieved by combining At-Least-Once processing with deduplication mechanisms (like database unique indexes or transaction locks).

### Transactional Outbox Pattern
When performing actions that involve writing to a database and triggering an external side effect (like sending an email or publishing to a message broker):
- **Do not** call the external service inside the database transaction. If the service is slow, it holds the DB connection open. If the transaction rolls back, the email cannot be unsent (dual-write problem).
- **Solution:** Use the Transactional Outbox pattern. Write both the primary state change (e.g., `ApproveGrant`) and a task record (e.g., `SendEmailJob`) to the database inside the same transaction. A separate background worker reads the outbox table and executes the side-effects.

### External Resources
- [Distributed Systems - Messaging Guarantees](https://en.wikipedia.org/wiki/Reliable_messaging)
- [Microservices Pattern: Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Wikipedia: Rule-Based System](https://en.wikipedia.org/wiki/Rule-based_system)

---

## HFC Rules

Score rules:

| Rule | Points |
|---|---:|
| Duplicate CNIC | 50 |
| Duplicate email | 20 |
| Duplicate mobile | 20 |
| Missing business profile | 30 |
| Missing required documents | 25 |
| Missing grant media | 10 |
| Business district out of scope | 40 |
| Grant amount above threshold | 15 |
| Application submitted very fast | 10 |
| Missing expression of interest | 15 |

Risk bands:

| Score | Level |
|---:|---|
| 0-29 | LOW |
| 30-59 | MEDIUM |
| 60-79 | HIGH |
| 80+ | CRITICAL |

---

## Tables

HFC writes:
- `hfc_evaluations`
- `hfc_review_actions`
- HFC fields on `grants`

Approval writes:
- `grants.status`
- `grants.approved_amount`
- `grants.approval_reason`
- `grants.approved_at`
- `grants.approved_by`
- `grant_approval_logs`

---

## Admin Endpoints

HFC:
- `GET /api/admin/hfc/dashboard/stats`
- `GET /api/admin/hfc/queue`
- `GET /api/admin/hfc/applicant/<user_id>`
- `POST /api/admin/hfc/applicant/<user_id>/action`
- `POST /api/admin/hfc/applicant/<user_id>/recalculate`

Approval:
- `GET /api/admin/grants/<user_id>/approval-check`
- `POST /api/admin/grants/<user_id>/approve`

---

## Shadow Mode

If `HFC_SHADOW_MODE=1`, HFC score does not block approval. The score is advisory.

If shadow mode is off, define explicit blocking behavior before implementation. For example, require override for HIGH/CRITICAL risk.

---

## Audit Trails

Every admin action should record:
- actor username
- action type
- before state
- after state
- comment
- timestamp

Audit records are not decoration. They are how an approval system explains itself later.

---

## Practical Examples

### Example: Implementing a Deterministic HFC Scorer in Go
This example shows how to write a scoring engine that queries various database tables and calculates a cumulative fraud score based on the application rules:

```go
// File: internal/hfc/scorer.go
package hfc

import (
	"context"
	"fmt"
)

type EvaluationResult struct {
	Score     int
	RiskLevel string
	Details   map[string]int
}

type ScorerRepository interface {
	CheckDuplicateCNIC(ctx context.Context, userID int64, cnic string) (bool, error)
	HasBusinessProfile(ctx context.Context, userID int64) (bool, error)
	GetUploadedDocumentsCount(ctx context.Context, userID int64) (int, error)
}

type Scorer struct {
	repo ScorerRepository
}

func NewScorer(repo ScorerRepository) *Scorer {
	return &Scorer{repo: repo}
}

// Evaluate calculates the risk score and risk bands for an applicant.
func (s *Scorer) Evaluate(ctx context.Context, userID int64, cnic string) (*EvaluationResult, error) {
	score := 0
	details := make(map[string]int)

	// Rule 1: Check for duplicate CNIC
	isDuplicateCNIC, err := s.repo.CheckDuplicateCNIC(ctx, userID, cnic)
	if err != nil {
		return nil, fmt.Errorf("failed to check duplicate CNIC: %w", err)
	}
	if isDuplicateCNIC {
		score += 50
		details["duplicate_cnic"] = 50
	}

	// Rule 2: Check for missing business profile
	hasProfile, err := s.repo.HasBusinessProfile(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("failed to check business profile: %w", err)
	}
	if !hasProfile {
		score += 30
		details["missing_business_profile"] = 30
	}

	// Rule 3: Check for incomplete documents (expecting 5 required uploads)
	uploadedCount, err := s.repo.GetUploadedDocumentsCount(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("failed to get docs count: %w", err)
	}
	if uploadedCount < 5 {
		score += 25
		details["missing_required_documents"] = 25
	}

	// Determine Risk Level Band
	var riskLevel string
	switch {
	case score <= 29:
		riskLevel = "LOW"
	case score <= 59:
		riskLevel = "MEDIUM"
	case score <= 79:
		riskLevel = "HIGH"
	default:
		riskLevel = "CRITICAL"
	}

	return &EvaluationResult{
		Score:     score,
		RiskLevel: riskLevel,
		Details:   details,
	}, nil
}
```

---

## Mastery Check

You understand this chapter when you can:
- Implement deterministic scoring from database facts.
- Store a full HFC evaluation record.
- Update grant HFC fields from latest evaluation.
- Restrict approval to `is_approver`.
- Record approval logs.
- Explain why shadow mode changes enforcement but not scoring.
