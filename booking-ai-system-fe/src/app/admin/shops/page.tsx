import { ShopList } from "@/features/shop/ShopList";

export default function AdminShopsPage() {
  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold text-zinc-900">Quản lý Shop</h1>
      <ShopList />
    </div>
  );
}
