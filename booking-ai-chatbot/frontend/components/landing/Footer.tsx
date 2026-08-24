import { ChatOpenButton } from "@/components/landing/ChatOpenButton";
import { navItems } from "@/components/landing/data";
import { Container } from "@/components/ui/Container";

export function Footer() {
  return (
    <footer className="site-footer">
      <Container className="footer-inner">
        <div>
          <strong>Kori Massage</strong>
          <p>Premium wellness booking with Kori AI Concierge.</p>
        </div>
        <nav aria-label="Liên kết cuối trang">
          {navItems.map((item) => (
            <a href={item.href} key={item.href}>
              {item.label}
            </a>
          ))}
        </nav>
        <ChatOpenButton variant="secondary">Subscribe</ChatOpenButton>
      </Container>
    </footer>
  );
}
