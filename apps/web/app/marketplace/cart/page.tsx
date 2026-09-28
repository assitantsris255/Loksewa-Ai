"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { marketplaceApi, Cart } from "@/lib/api/marketplace";
import { ArrowRight, Loader2, Minus, Plus, ShoppingBag, Trash2 } from "lucide-react";

export default function CartPage() {
  const router = useRouter();
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<number | null>(null);

  const fetchCart = async () => {
    try {
      const data = await marketplaceApi.getCart();
      setCart(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCart();
  }, []);

  const updateQuantity = async (itemId: number, currentQty: number, delta: number) => {
    const newQty = currentQty + delta;
    if (newQty < 1) return;
    setUpdating(itemId);
    try {
      await marketplaceApi.updateCartItem(itemId, newQty);
      await fetchCart();
    } catch (err: any) {
      alert(err.message || "Failed to update quantity");
    } finally {
      setUpdating(null);
    }
  };

  const removeItem = async (itemId: number) => {
    setUpdating(itemId);
    try {
      await marketplaceApi.removeFromCart(itemId);
      await fetchCart();
    } catch (err: any) {
      alert(err.message || "Failed to remove item");
    } finally {
      setUpdating(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-[#0A1118] flex items-center justify-center flex-col">
        <Loader2 className="w-10 h-10 animate-spin text-[#163E6B]" />
      </div>
    );
  }

  const items = cart?.items || [];
  const subtotal = items.reduce((sum, item) => {
    const price = item.product_details?.final_price ? parseFloat(item.product_details.final_price) : 0;
    return sum + price * item.quantity;
  }, 0);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#0A1118] text-slate-900 dark:text-slate-50 flex flex-col font-sans">
      <main className="flex-1 container mx-auto px-4 py-24 max-w-5xl">
        <h1 className="text-3xl font-extrabold mb-8 flex items-center gap-3">
          <ShoppingBag className="w-8 h-8 text-[#163E6B] dark:text-[#D4A72C]" /> Your Cart
        </h1>

        {items.length === 0 ? (
          <div className="bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-2xl p-12 text-center flex flex-col items-center justify-center">
            <ShoppingBag className="w-16 h-16 text-slate-300 dark:text-white/20 mb-4" />
            <h2 className="text-xl font-bold mb-2">Your cart is empty</h2>
            <p className="text-slate-500 mb-6">Looks like you haven't added anything to your cart yet.</p>
            <Button onClick={() => router.push("/marketplace")}>Continue Shopping</Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-2 space-y-4">
              {items.map((item) => {
                const product = item.product_details;
                if (!product) return null;
                const price = parseFloat(product.final_price);

                return (
                  <div key={item.id} className="flex flex-col sm:flex-row items-start sm:items-center gap-4 bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-2xl p-4">
                    <div className="w-24 h-24 bg-slate-100 dark:bg-white/10 rounded-xl overflow-hidden shrink-0">
                      {product.cover_image && <img src={product.cover_image} alt={product.title} className="w-full h-full object-cover" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-bold text-[#163E6B] dark:text-[#D4A72C] mb-1">{product.category}</div>
                      <h3 className="text-lg font-bold truncate mb-1">{product.title}</h3>
                      <div className="text-sm text-slate-500 mb-2">Rs. {price.toFixed(2)}</div>
                      
                      <div className="flex items-center gap-4">
                        <div className="flex items-center border border-slate-200 dark:border-white/10 rounded-lg">
                          <button 
                            className="w-8 h-8 flex items-center justify-center hover:bg-slate-100 dark:hover:bg-white/10 rounded-l-lg disabled:opacity-50"
                            onClick={() => updateQuantity(item.id, item.quantity, -1)}
                            disabled={updating === item.id || item.quantity <= 1}
                          >
                            <Minus className="w-3 h-3" />
                          </button>
                          <span className="w-10 text-center text-sm font-semibold">{updating === item.id ? <Loader2 className="w-3 h-3 animate-spin mx-auto" /> : item.quantity}</span>
                          <button 
                            className="w-8 h-8 flex items-center justify-center hover:bg-slate-100 dark:hover:bg-white/10 rounded-r-lg disabled:opacity-50"
                            onClick={() => updateQuantity(item.id, item.quantity, 1)}
                            disabled={updating === item.id}
                          >
                            <Plus className="w-3 h-3" />
                          </button>
                        </div>
                        <button 
                          className="text-red-500 hover:text-red-600 p-2"
                          onClick={() => removeItem(item.id)}
                          disabled={updating === item.id}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                    <div className="text-right sm:text-left mt-4 sm:mt-0 font-bold text-lg shrink-0">
                      Rs. {(price * item.quantity).toFixed(2)}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-2xl p-6 h-fit sticky top-24">
              <h3 className="text-xl font-bold mb-4">Order Summary</h3>
              <div className="space-y-3 mb-6">
                <div className="flex justify-between text-slate-600 dark:text-slate-400">
                  <span>Subtotal</span>
                  <span>Rs. {subtotal.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-slate-600 dark:text-slate-400">
                  <span>Delivery Charge</span>
                  <span>Calculated at checkout</span>
                </div>
                <div className="pt-3 border-t border-slate-200 dark:border-white/10 flex justify-between font-extrabold text-lg">
                  <span>Total</span>
                  <span>Rs. {subtotal.toFixed(2)}</span>
                </div>
              </div>
              <Button 
                className="w-full h-12 text-lg font-bold bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118]"
                onClick={() => router.push("/marketplace/checkout")}
              >
                Proceed to Checkout <ArrowRight className="w-5 h-5 ml-2" />
              </Button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
