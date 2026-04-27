rocketcoach.app, www.rocketcoach.app {
  encode gzip

  reverse_proxy 127.0.0.1:8888 {
    header_up Host {host}
    header_up X-Forwarded-Host {host}
    header_up X-Forwarded-Proto {scheme}
  }
}
