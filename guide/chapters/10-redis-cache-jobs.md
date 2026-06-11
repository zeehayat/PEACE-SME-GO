# Chapter 10: Redis, Caching, Access Slots, and Background Jobs

## Purpose

Redis supports three separate concerns in this application: JSON response caching, concurrent applicant access control, and background job queues and HFC debounce. In this chapter, we will study **Concurrency in Go**, learning how to spawn lightweight processes (Goroutines), communicate safely between them (Channels), and coordinate operations using `select` blocks. We will then implement a background worker queue pool.

---

## Foundational Concepts Explained Simply

### 1. Goroutines
A **Goroutine** is a lightweight thread of execution managed by the Go runtime.
- **Spawning:** Prefix any function call with the `go` keyword (e.g. `go doWork()`). This runs the function concurrently in the background.
- **Cost:** Spawning a goroutine is extremely cheap. They start with only ~2KB of stack space and grow dynamically, allowing you to spawn tens of thousands concurrently.

### 2. Channels
In Go, instead of sharing memory between threads using complex locks, goroutines communicate by sending and receiving messages over **Channels**. Channels are type-safe conduits.
- **Syntax:**
  - Create: `ch := make(chan int)` (unbuffered) or `ch := make(chan int, 100)` (buffered).
  - Send: `ch <- 42` (sends 42 into the channel).
  - Receive: `val := <-ch` (blocks execution until a value is read from the channel).
  - Close: `close(ch)` (notifies receivers that no more values will be sent).
- **Blocking:** 
  - Sends/receives on an **unbuffered** channel block until both the sender and receiver are ready.
  - **Buffered** channels block only when the buffer is full (on sends) or empty (on receives).

### 3. Select Statements
The `select` statement lets a goroutine wait on multiple channel operations.
- It blocks until one of its cases is ready to execute.
- If multiple cases are ready, it chooses one pseudo-randomly.
- You can add a `default` case to make operations non-blocking.

Here is an example demonstrating goroutines, channels, and select coordination:

```go
package main

import (
	"fmt"
	"time"
)

func worker(jobs <-chan int, results chan<- int) {
	for job := range jobs {
		fmt.Printf("Processing job %d\n", job)
		time.Sleep(100 * time.Millisecond) // Simulate slow job
		results <- job * 2                 // Send result back
	}
}

func main() {
	jobs := make(chan int, 10)
	results := make(chan int, 10)

	// Spawn a background worker goroutine
	go worker(jobs, results)

	// Send 3 jobs
	for i := 1; i <= 3; i++ {
		jobs <- i
	}
	close(jobs) // Close jobs to signal worker to finish loop

	// Collect results using select
	for i := 1; i <= 3; i++ {
		select {
		case res := <-results:
			fmt.Println("Result received:", res)
		case <-time.After(500 * time.Millisecond):
			fmt.Println("Timeout waiting for result!")
		}
	}
}
```

### External Resources
- [A Tour of Go: Goroutines](https://go.dev/tour/concurrency/1)
- [A Tour of Go: Channels](https://go.dev/tour/concurrency/2)
- [Go Web Examples: Channels](https://gowebexamples.com/channels/)

---

## Cache Wrapper

Create a small package:

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

## Cached Data

Cache:
- Updates: 3600 seconds.
- FAQs: 300 seconds.
- Dashboard stats: 60 seconds.
- Report filter options: 120 seconds.

Invalidate content caches after admin creates, updates, or deletes FAQs and updates.

---

## Access Slots

The Flask pipeline limits active applicants:
- `ACCESS_CONTROL_ENABLED=1`
- `MAX_ACTIVE_APPLICANTS=300`
- `ACCESS_SLOT_TTL_SEC=90`

In Go:
1. Determine session ID.
2. `SETEX peace_sme:session:<id> 90 1`
3. Count active session keys.
4. Return 429 if the limit is exceeded.

For production scale, avoid expensive `KEYS`; prefer `SCAN` or a sorted-set design. Preserve behavior first, optimize second.

---

## Background Jobs

The original uses RQ queues:
- `emails`
- `hfc`

In Go, choose one of two paths:
1. Keep compatibility with existing Redis queue format while migrating gradually.
2. Build a Go worker with explicit Redis streams/lists and migrate worker behavior too.

For learning, start with an interface:

```go
type JobQueue interface {
    EnqueueEmail(ctx context.Context, job EmailJob) error
    EnqueueHFC(ctx context.Context, userID int64) error
}
```

Then implement Redis behind it.

---

## HFC Debounce

Before enqueueing HFC:
- Set a Redis debounce key for user ID.
- If key already exists, skip enqueue.
- TTL comes from `HFC_ENQUEUE_DEBOUNCE_SEC`, default 60.

---

## Practical Examples

### Example 1: Caching Helper with JSON Serialization
This helper maps database objects into Redis string keys using JSON marshaling:

```go
// File: internal/cache/redis.go
package cache

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

type Cache struct {
	client *redis.Client
	prefix string
}

func NewCache(client *redis.Client, prefix string) *Cache {
	return &Cache{client: client, prefix: prefix}
}

func (c *Cache) makeKey(key string) string {
	return fmt.Sprintf("%s:%s", c.prefix, key)
}

// GetJSON retrieves a cached item and unmarshals it into dst.
func (c *Cache) GetJSON(ctx context.Context, key string, dst interface{}) (bool, error) {
	fullKey := c.makeKey(key)
	val, err := c.client.Get(ctx, fullKey).Result()
	if err == redis.Nil {
		return false, nil // Cache miss
	} else if err != nil {
		return false, fmt.Errorf("redis read error: %w", err)
	}

	if err := json.Unmarshal([]byte(val), dst); err != nil {
		return false, fmt.Errorf("failed to unmarshal cached data: %w", err)
	}

	return true, nil // Cache hit
}

// SetJSON marshals an item and stores it with a TTL.
func (c *Cache) SetJSON(ctx context.Context, key string, value interface{}, ttl time.Duration) error {
	fullKey := c.makeKey(key)
	bytes, err := json.Marshal(value)
	if err != nil {
		return fmt.Errorf("failed to marshal cache value: %w", err)
	}

	return c.client.Set(ctx, fullKey, bytes, ttl).Err()
}
```

### Example 2: Goroutine Worker Pool for Processing Job Channels
This background processor pools jobs from a Go channel and executes them concurrently using separate worker goroutines:

```go
// File: internal/worker/pool.go
package worker

import (
	"context"
	"log"
	"sync"
)

type EmailJob struct {
	To      string
	Subject string
	Body    string
}

type WorkerPool struct {
	jobChan    chan EmailJob
	numWorkers int
	wg         sync.WaitGroup
}

func NewWorkerPool(numWorkers int, bufferSize int) *WorkerPool {
	return &WorkerPool{
		jobChan:    make(chan EmailJob, bufferSize),
		numWorkers: numWorkers,
	}
}

// Start spawns the worker goroutines.
func (p *WorkerPool) Start(ctx context.Context) {
	for i := 1; i <= p.numWorkers; i++ {
		p.wg.Add(1)
		go p.worker(ctx, i) // Spawn concurrently
	}
}

// worker loops reading from the shared job channel.
func (p *WorkerPool) worker(ctx context.Context, workerID int) {
	defer p.wg.Done()
	log.Printf("Background worker %d started.", workerID)

	for {
		select {
		case <-ctx.Done():
			log.Printf("Worker %d received shutdown signal.", workerID)
			return
		case job, ok := <-p.jobChan:
			if !ok {
				log.Printf("Worker %d channel closed. Exiting.", workerID)
				return
			}
			
			// Process job
			p.executeJob(job, workerID)
		}
	}
}

func (p *WorkerPool) executeJob(job EmailJob, workerID int) {
	log.Printf("[Worker %d] Processing email to %s, Subject: %q", workerID, job.To, job.Subject)
	// actual integration sending goes here...
}

// Enqueue puts a job into the buffered channel.
func (p *WorkerPool) Enqueue(job EmailJob) {
	p.jobChan <- job
}

// Stop closes the channel and waits for workers to drain it.
func (p *WorkerPool) Stop() {
	close(p.jobChan)
	p.wg.Wait()
	log.Println("Worker pool stopped cleanly.")
}
```

---

## Mastery Check

You understand this chapter when you can:
- Explain what goroutines are and why they are lightweight.
- Create unbuffered and buffered channels.
- Send and receive values on channels without locking threads.
- Coordinate multiple channels using `select` statements.
- Write a clean worker loop that drains channels safely.
