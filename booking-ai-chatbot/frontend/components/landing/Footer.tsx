import { navItems } from "@/components/landing/data";
import { Container } from "@/components/ui/Container";

export function Footer() {
  return (
    <footer className="site-footer">
      <Container className="footer-inner">
        <strong>Komorebi Spa</strong>
        <nav aria-label="Liên kết cuối trang">
          {navItems.map((item) => (
            <a href={item.href} key={item.href}>{item.label}</a>
          ))}
        </nav>
      </Container>
    </footer>
  );
}
