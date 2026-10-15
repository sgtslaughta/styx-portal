// Package styxlocation rewrites absolute redirects that point at a configured
// host into origin-relative ones, so a browser stays on the Styx hostname.
// Stdlib only and plain Go (no generics, no embedding) to stay Yaegi-friendly.
package styxlocation

import (
	"bufio"
	"context"
	"errors"
	"net"
	"net/http"
	"net/url"
	"strings"
)

// Config is the plugin configuration.
type Config struct {
	Host string `json:"host,omitempty"`
}

// CreateConfig returns the default configuration.
func CreateConfig() *Config { return &Config{} }

type rewriter struct {
	next http.Handler
	host string
}

// New creates the middleware.
func New(ctx context.Context, next http.Handler, config *Config, name string) (http.Handler, error) {
	if config == nil || strings.TrimSpace(config.Host) == "" {
		return nil, errors.New("styxlocation: host must not be empty")
	}
	return &rewriter{next: next, host: strings.ToLower(strings.TrimSpace(config.Host))}, nil
}

func (r *rewriter) ServeHTTP(rw http.ResponseWriter, req *http.Request) {
	r.next.ServeHTTP(&writer{rw: rw, host: r.host}, req)
}

// relative returns the origin-relative form of v when it is absolute (or
// scheme-relative) and targets host; otherwise v unchanged.
func relative(v, host string) string {
	if !strings.HasPrefix(v, "//") && !strings.Contains(v, "://") {
		return v
	}
	u, err := url.Parse(v)
	if err != nil || u.Host == "" || strings.ToLower(u.Hostname()) != host {
		return v
	}
	out := u.EscapedPath()
	if out == "" {
		out = "/"
	}
	if u.ForceQuery || u.RawQuery != "" {
		out += "?" + u.RawQuery
	}
	if u.Fragment != "" {
		out += "#" + u.EscapedFragment()
	}
	return out
}

// refresh rewrites the target of "N; url=<abs>".
func refresh(v, host string) string {
	i := strings.Index(strings.ToLower(v), "url=")
	if i < 0 {
		return v
	}
	return v[:i+4] + relative(strings.TrimSpace(v[i+4:]), host)
}

type writer struct {
	rw   http.ResponseWriter
	host string
	sent bool
}

func (w *writer) Header() http.Header { return w.rw.Header() }

func (w *writer) rewrite() {
	if w.sent {
		return
	}
	w.sent = true
	h := w.rw.Header()
	if v := h.Get("Location"); v != "" {
		h.Set("Location", relative(v, w.host))
	}
	if v := h.Get("Refresh"); v != "" {
		h.Set("Refresh", refresh(v, w.host))
	}
}

func (w *writer) WriteHeader(code int) {
	w.rewrite()
	w.rw.WriteHeader(code)
}

func (w *writer) Write(b []byte) (int, error) {
	w.rewrite()
	return w.rw.Write(b)
}

func (w *writer) Flush() {
	w.rewrite()
	if f, ok := w.rw.(http.Flusher); ok {
		f.Flush()
	}
}

func (w *writer) Hijack() (net.Conn, *bufio.ReadWriter, error) {
	h, ok := w.rw.(http.Hijacker)
	if !ok {
		return nil, nil, errors.New("styxlocation: underlying writer is not a Hijacker")
	}
	return h.Hijack()
}
