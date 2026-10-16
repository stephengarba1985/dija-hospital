const nextConfig = {
  agentRules: false,
  devIndicators: false,
  trailingSlash: true,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: '/api/:path*/', destination: `${process.env.DJANGO_ORIGIN || 'http://127.0.0.1:8000'}/api/:path*/` }];
  },
  async headers() {
    return [{ source: '/:path*', headers: [
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'Referrer-Policy', value: 'same-origin' },
      { key: 'Cache-Control', value: 'no-store' },
    ] }];
  },
};
export default nextConfig;
