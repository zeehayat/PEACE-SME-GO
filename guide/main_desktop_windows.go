//go:build windows

package main

import (
	"embed"
	"fmt"
	"net"
	"net/http"
	"os"

	webview "github.com/jchv/go-webview2"
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

	// Create WebView2 window
	debug := false
	w := webview.New(debug)
	if w == nil {
		fmt.Fprintln(os.Stderr, "Failed to initialize native WebView2 window.")
		fmt.Fprintln(os.Stderr, "Please ensure Microsoft Edge WebView2 Runtime is installed.")
		os.Exit(1)
	}
	defer w.Destroy()

	w.SetTitle("PEACE SME Grant System - Mastery & Help Portal")
	w.SetSize(1150, 780, webview.HintNone)

	// Navigate to the local HTTP server
	url := fmt.Sprintf("http://127.0.0.1:%d", port)
	w.Navigate(url)

	// Run window event loop (blocks until window is closed)
	w.Run()
}
