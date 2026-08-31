import Image from "next/image";

interface WellnessImageProps {
  src: string;
  alt: string;
  className?: string;
  priority?: boolean;
  sizes?: string;
}

// Wrapper ảnh dùng chung để Next/Image có layout fill ổn định trong các khung visual khác nhau.
export function WellnessImage({
  src,
  alt,
  className = "",
  priority = false,
  sizes = "(max-width: 900px) 100vw, 50vw",
}: WellnessImageProps) {
  return (
    <div className={`wellness-image${className ? ` ${className}` : ""}`}>
      <Image
        src={src}
        alt={alt}
        fill
        priority={priority}
        sizes={sizes}
      />
    </div>
  );
}
