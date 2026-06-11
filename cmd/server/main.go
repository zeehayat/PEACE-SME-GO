package main

import (
	"log"
	"net/http"
	"time"
)

type Server struct {
	Addr string
}

func NewServer(addr string) *Server {
	return &Server{Addr: addr}
}
func (s *Server) Start() error {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/health", func(w http.ResponseWriter, r *http.Request) {
		_, err := w.Write([]byte(`{"status":"healthy"`))
		if err != nil {
			return
		}
	})
	srv := &http.Server{
		Addr:         s.Addr,
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
	}
	log.Printf("Bootstrapping server on %s", s.Addr)
	return srv.ListenAndServe()
}
func main() {

	srv := NewServer(":8000")
	if err := srv.Start(); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}

}
