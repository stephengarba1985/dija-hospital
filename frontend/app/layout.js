import './globals.css';

export const metadata = {
  title: 'Dija Hospital | Hospital management',
  description: 'A connected workspace for Dija Hospital, Nigeria.',
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }) {
  return <html lang="en-NG"><body>{children}</body></html>;
}
