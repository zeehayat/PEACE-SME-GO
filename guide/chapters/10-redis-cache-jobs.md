# Chapter 10: Redis, Caching, Access Slots, and Background Jobs

## Purpose

Redis supports three separate concerns in this application: JSON response caching, concurrent applicant access control, and background job queues. In this chapter, we will study **Go Concurrency**, explaining lightweight threads (Goroutines), communication pipes (Channels), and select statements. We will then define **every channel and worker coordination loop** required by the portal.

---

## Foundational Concepts Explained Simply

### 1. Goroutines

:::expandable [Goroutines: Lightweight Concurrent Threads]
#### In-Depth Explanation
In Go, concurrency is achieved using **Goroutines**, which are lightweight, user-space threads managed entirely by the Go runtime scheduler rather than the underlying Operating System.
* **OS Threads vs. Goroutines:** OS threads typically consume about 1MB of memory for their stack space. In contrast, a Goroutine starts with a dynamic, resizable stack of only **2KB**.
* **Spawning:** Prefixing any function call with the `go` keyword schedules the function to run concurrently. The current thread continues executing immediately without blocking.
* **Go Scheduler:** Go uses an M:N scheduler, multiplexing thousands of active Goroutines (N) onto a small number of physical OS threads (M). This eliminates the expensive context-switching overhead of OS thread shifts.

#### Sandbox Program: Spawning Concurrent Tasks
This program demonstrates spawning multiple independent background tasks concurrently using the `go` keyword and coordinates their execution using a simple time delay:

```go
package main

import (
	"fmt"
	"time"
)

func runAuditRule(ruleName string, duration time.Duration) {
	fmt.Printf("[HFC AUDIT] Starting risk evaluation: %s\n", ruleName)
	time.Sleep(duration) // Simulate computational rule check
	fmt.Printf("[HFC AUDIT] Finished risk evaluation: %s\n", ruleName)
}

func main() {
	fmt.Println("Main thread: Initiating background evaluation pipeline.")

	// Spawn two background concurrent tasks
	go runAuditRule("Verify CNIC Format", 50*time.Millisecond)
	go runAuditRule("Check Allowed IP Region", 30*time.Millisecond)

	fmt.Println("Main thread: Handlers returned immediately. Sleeping to allow worker tasks to finish...")
	
	// Wait long enough for both tasks to complete
	time.Sleep(100 * time.Millisecond)
	fmt.Println("Main thread: Shutting down.")
}
```
:::

### 2. Channels

:::expandable [Go Channels & Synchronous Communication]
#### In-Depth Explanation
Go's concurrency philosophy is: *"Do not communicate by sharing memory; instead, share memory by communicating."*
* **Channels (`chan T`):** Type-safe pipes that allow separate Goroutines to synchronize and exchange messages without explicit locks or mutexes.
* **Buffered vs. Unbuffered:**
  * **Unbuffered (`make(chan T)`):** Sends and receives block until both the sender and receiver are ready. This guarantees synchronous handoffs.
  * **Buffered (`make(chan T, size)`):** Sends are non-blocking as long as the buffer is not full. Receives are non-blocking as long as the buffer is not empty.
* **Graceful Channel Closing:** The sender can close a channel using `close(ch)`. Receivers can test if a channel is closed using the comma-ok idiom: `val, ok := <-ch`. If `ok` is `false`, the channel has been drained and closed.

#### Sandbox Program: Channel Coordination and Draining
This program runs a worker that receives work from a buffered channel and communicates results back, showing how channel closes signal completion:

```go
package main

import (
	"fmt"
)

func jobProcessor(jobs <-chan int, results chan<- int) {
	for job := range jobs {
		// Process job
		double := job * 2
		results <- double
	}
	close(results) // Close results channel when all jobs are processed
}

func main() {
	jobs := make(chan int, 3)
	results := make(chan int, 3)

	// Start processor
	go jobProcessor(jobs, results)

	// Send 3 jobs
	jobs <- 10
	jobs <- 20
	jobs <- 30
	close(jobs) // Signal that no more jobs will be sent

	// Read results
	for res := range results {
		fmt.Println("Job Result Received:", res)
	}
	fmt.Println("All channel items processed successfully.")
}
```
:::

### 3. Select Statements

:::expandable [Select Block Coordination & Timeouts]
#### In-Depth Explanation
The `select` statement enables a Goroutine to wait on multiple channel communication operations simultaneously.
* **Multiplexing:** It blocks until one of its cases is ready to send or receive. If multiple cases are ready, it picks one at random.
* **Timeouts:** Combined with `time.After(duration)`, it prevents deadlocks by establishing a maximum wait limit. If no channel responds within the limit, the timeout case fires.
* **Non-blocking Select:** A `default` case causes the `select` statement to proceed immediately without blocking if no other channels are ready.

#### Sandbox Program: Job Queue Coordination with Timeout
This program uses a `select` statement to process messages from multiple queues and includes a timeout protection block:

```go
package main

import (
	"fmt"
	"time"
)

func main() {
	emailQueue := make(chan string, 1)
	hfcQueue := make(chan string, 1)

	// Simulate background worker loading
	go func() {
		time.Sleep(20 * time.Millisecond)
		emailQueue <- "Welcome Email for User 42"
	}()

	// Read loop with timeout
	for i := 0; i < 2; i++ {
		select {
		case email := <-emailQueue:
			fmt.Println("Processed Queue Item:", email)
		case hfc := <-hfcQueue:
			fmt.Println("Processed Queue Item:", hfc)
		case <-time.After(50 * time.Millisecond):
			fmt.Println("Job dispatch timed out!")
		}
	}
}
```
:::

### External Resources
- [A Tour of Go: Goroutines](https://go.dev/tour/concurrency/1)
- [A Tour of Go: Channels](https://go.dev/tour/concurrency/2)
- [Go Web Examples: Channels](https://gowebexamples.com/channels/)

---

## Phased Concurrency Implementation Guide

To master concurrency, we will now define **all channel-based background workers and job queues** required by the PEACE SME Grant Portal.

Create a file named [internal/worker/queues.go](file:///var/www/peace-sme-go/internal/worker/queues.go) to declare these structures.

### 1. Job Structs
First, define the structures representing background tasks:

```go
package worker

// EmailJob wraps the parameters needed to send welcome and approval alerts.
type EmailJob struct {
	RecipientEmail string `json:"recipient_email"`
	Subject        string `json:"subject"`
	Body           string `json:"body"`
}

// HFCJob wraps parameters needed to trigger HFC fraud risk scoring.
type HFCJob struct {
	UserID    int64 `json:"user_id"`
	IsTriggeredByAdmin bool `json:"is_triggered_by_admin"`
}
```

### 2. The Worker Manager
The `Manager` struct acts as a coordinator, maintaining the channels and controlling worker lifecycles:

```go
import (
	"context"
	"log"
	"sync"
)

// Manager coordinates job queues and background execution routines.
type Manager struct {
	EmailQueue chan EmailJob // Buffered channel for emails
	HFCQueue   chan HFCJob   // Buffered channel for HFC jobs
	wg         sync.WaitGroup
	shutdown   chan struct{}
}

// NewManager initializes the queues with buffer sizes.
func NewManager(bufferSize int) *Manager {
	return &Manager{
		EmailQueue: make(chan EmailJob, bufferSize),
		HFCQueue:   make(chan HFCJob, bufferSize),
		shutdown:   make(chan struct{}),
	}
}

// Start begins background execution loop goroutines.
func (m *Manager) Start(ctx context.Context) {
	// Start email processor worker
	m.wg.Add(1)
	go m.emailWorker(ctx)

	// Start HFC processor worker
	m.wg.Add(1)
	go m.hfcWorker(ctx)
}

func (m *Manager) emailWorker(ctx context.Context) {
	defer m.wg.Done()
	log.Println("Email worker started.")

	for {
		select {
		case <-ctx.Done():
			log.Println("Email worker shutting down...")
			return
		case job, ok := <-m.EmailQueue:
			if !ok {
				return
			}
			m.sendEmail(job)
		}
	}
}

func (m *Manager) hfcWorker(ctx context.Context) {
	defer m.wg.Done()
	log.Println("HFC worker started.")

	for {
		select {
		case <-ctx.Done():
			log.Println("HFC worker shutting down...")
			return
		case job, ok := <-m.HFCQueue:
			if !ok {
				return
			}
			m.evaluateHFC(job)
		}
	}
}

func (m *Manager) sendEmail(job EmailJob) {
	log.Printf("[EMAIL] Sending message to %s: %s", job.RecipientEmail, job.Subject)
	// actual SMTP/Brevo integration calls...
}

func (m *Manager) evaluateHFC(job HFCJob) {
	log.Printf("[HFC] Re-evaluating rules for User ID %d", job.UserID)
	// actual database/HFC scoring rules checks...
}

// Stop closes channels and blocks until workers drain existing jobs safely.
func (m *Manager) Stop() {
	close(m.EmailQueue)
	close(m.HFCQueue)
	m.wg.Wait()
	log.Println("All background queue workers stopped.")
}
```

---

## Cache Wrapper

Create a small package `internal/cache/redis.go` to wrap Redis JSON access caching:

```go
type Cache struct {
    client *redis.Client
    prefix string
}
```

Methods:
- `GetJSON(ctx, key, &dst)`
- `SetJSON(ctx, key, value, ttl)`
- `DeletePrefix(ctx, prefix)`

Use the configured prefix, defaulting to `peace_sme`.

---

## Mastery Check

You understand this chapter when you can:
- Explain what goroutines are and why they are lightweight.
- Create unbuffered and buffered channels.
- Coordinate multiple channel reads concurrently using `select`.
- Build a thread-safe worker coordinator using `sync.WaitGroup` to handle graceful shutdowns.
