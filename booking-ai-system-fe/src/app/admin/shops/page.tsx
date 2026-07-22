import { ShopList } from "@/features/shop/ShopList";

export default function AdminShopsPage() {
  return (
    <section className="mx-auto w-full max-w-7xl min-w-0">
      <header className="mb-4">
        <h1 className="text-xl font-semibold tracking-tight text-zinc-900 sm:text-2xl">
          Quản lý shop
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          Theo dõi mã kết nối, thông tin liên hệ và trạng thái từng chi nhánh.
        </p>
      </header>
      <ShopList />
    </section>
  );
}
