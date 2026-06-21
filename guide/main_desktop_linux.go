//go:build !windows

package main

import (
	"embed"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"

	"github.com/zserge/lorca"
)

//go:embed index.html
var fs embed.FS

func main() {
	// Start local server to serve the embedded index.html
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to start local help server: %v\n", err)
		os.Exit(1)
	}
	port := listener.Addr().(*net.TCPAddr).Port

	// Set up handler to serve index.html directly from embed
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		data, err := fs.ReadFile("index.html")
		if err != nil {
			http.Error(w, "File not found", http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write(data)
	})

	srv := &http.Server{}
	go func() {
		if err := srv.Serve(listener); err != http.ErrServerClosed {
			fmt.Fprintf(os.Stderr, "Local server closed with error: %v\n", err)
		}
	}()
	defer srv.Close()

	// Launch Lorca UI pointing to local server
	// Parameters: URL, user profile directory, window width, window height, additional Chrome flags
	ui, err := lorca.New(fmt.Sprintf("http://127.0.0.1:%d", port), "", 1150, 780, "--app", "--remote-allow-origins=*", "--no-sandbox", "--disable-setuid-sandbox")
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to initialize native help window: %v\n", err)
		fmt.Fprintln(os.Stderr, "Please ensure Microsoft Edge or Google Chrome is installed on this system.")
		os.Exit(1)
	}
	defer ui.Close()

	// Set the title of the window
	ui.Eval("document.title = 'PEACE SME Grant System - Mastery & Help Portal'")

	// Wait until window is closed or process is interrupted
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	select {
	case <-sigChan:
	case <-ui.Done():
	}
}
