"use client";

import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { marketplaceApi, Cart, Order, PaymentMethod } from "@/lib/api/marketplace";
import { ArrowLeft, ArrowRight, CheckCircle2, ImageIcon, UploadCloud, X, AlertCircle } from "lucide-react";
import { PageSkeleton, ButtonSpinner } from "@/components/ui/loading-states";

export default function CheckoutPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [cart, setCart] = useState<Cart | null>(null);
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Step 1: Customer Details
  const [address, setAddress] = useState("");
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");
  const [processingOrder, setProcessingOrder] = useState(false);
  const [createdOrder, setCreatedOrder] = useState<Order | null>(null);
  
  // Step 2: Payment
  const [selectedMethodId, setSelectedMethodId] = useState<number | null>(null);
  const [txnCode, setTxnCode] = useState("");
  const [screenshot, setScreenshot] = useState<File | null>(null);
  const [submittingPayment, setSubmittingPayment] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    Promise.all([
      marketplaceApi.getCart(),
      marketplaceApi.getPaymentMethods()
    ])
      .then(([cartData, methodsData]) => {
        setCart(cartData);
        if (cartData.items.length === 0) {
          router.push("/marketplace");
        }
        setPaymentMethods(methodsData);
        if (methodsData.length > 0 && methodsData[0]?.id) setSelectedMethodId(methodsData[0].id);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  }, [router]);

  const handleContinueToPayment = async () => {
    if (hasPhysicalItems && (!address.trim() || !phone.trim())) {
      alert("Please fill in address and phone number for physical delivery.");
      return;
    }
    
    setProcessingOrder(true);
    try {
      const order = await marketplaceApi.createOrder({
        shipping_address: address,
        contact_number: phone,
        note: notes
      });
      setCreatedOrder(order);
      setStep(2);
    } catch (err: any) {
      alert(err.message || "Failed to create order. Please try again.");
    } finally {
      setProcessingOrder(false);
    }
  };

  const handlePlaceOrder = async () => {
    if (!selectedMethodId) {
      alert("Please select a payment method.");
      return;
    }
    if (!txnCode.trim() || !screenshot || !createdOrder) {
      alert("Please provide transaction code and upload screenshot.");
      return;
    }

    setSubmittingPayment(true);
    try {
      const formData = new FormData();
      
      formData.append("order", createdOrder.id.toString());
      formData.append("payment_method", selectedMethodId.toString());
      formData.append("transaction_id", txnCode);
      formData.append("screenshot", screenshot);
      if (notes) formData.append("note", notes);

      await marketplaceApi.submitPayment(formData);
      setStep(3);
    } catch (err: any) {
      alert(err.message || "Payment verification failed.");
    } finally {
      setSubmittingPayment(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-[#0A1118] flex flex-col justify-between">
        <main className="flex-1 max-w-6xl mx-auto w-full py-10 px-4">
          <PageSkeleton layout="detail" />
        </main>
      </div>
    );
  }

  const items = cart?.items || [];
  const hasPhysicalItems = items.some(item => ['NEW_BOOK', 'USED_BOOK', 'STATIONERY'].includes(item.product_details?.category || ''));
  const subtotal = items.reduce((sum, item) => {
    const price = item.product_details?.final_price ? parseFloat(item.product_details.final_price) : 0;
    return sum + price * item.quantity;
  }, 0);
  const totalAmount = createdOrder ? parseFloat(createdOrder.total_amount) : subtotal;

  const renderOrderSummary = () => (
    <div className="bg-slate-50 dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-2xl p-6 h-fit sticky top-24">
      <h3 className="text-xl font-bold mb-6">Order Summary</h3>
      <div className="space-y-4 mb-6">
        {items.map((item) => (
          <div key={item.id} className="flex gap-4">
            <div className="w-16 h-16 bg-slate-100 dark:bg-white/10 rounded-xl overflow-hidden shrink-0">
              {item.product_details?.cover_image && <img src={item.product_details.cover_image} alt="" className="w-full h-full object-cover" />}
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-bold truncate">{item.product_details?.title}</h4>
              <p className="text-xs text-slate-500">Qty: {item.quantity} × Rs. {item.product_details?.final_price}</p>
            </div>
            <div className="text-sm font-bold shrink-0">
              Rs. {parseFloat(item.product_details?.final_price || "0") * item.quantity}
            </div>
          </div>
        ))}
      </div>
      <div className="pt-6 border-t border-slate-200 dark:border-white/10 space-y-3 font-semibold">
        <div className="flex justify-between text-slate-600 dark:text-slate-400 text-sm">
          <span>Subtotal</span>
          <span>Rs. {subtotal}</span>
        </div>
        <div className="pt-4 border-t border-slate-200 dark:border-white/10 flex justify-between text-lg font-bold">
          <span>Total</span>
          <span>Rs. {totalAmount}</span>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#0A1118] text-slate-900 dark:text-slate-50 flex flex-col font-sans">
      <main className="flex-1 container mx-auto px-4 py-24 max-w-6xl">
        <div className="flex justify-between items-center mb-12">
          <button onClick={() => router.push("/marketplace/cart")} className="flex items-center text-sm font-semibold text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors">
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Cart
          </button>
          <div className="flex items-center gap-4 text-sm font-bold">
            <div className={`flex items-center gap-2 ${step >= 1 ? 'text-[#163E6B] dark:text-[#D4A72C]' : 'text-slate-400'}`}>1. Details</div>
            <ArrowRight className="w-4 h-4 text-slate-300" />
            <div className={`flex items-center gap-2 ${step >= 2 ? 'text-[#163E6B] dark:text-[#D4A72C]' : 'text-slate-400'}`}>2. Payment</div>
          </div>
        </div>

        {step === 1 && (
          <div className="grid grid-cols-1 lg:grid-cols-[1.5fr_1fr] gap-12">
            <div className="space-y-6">
                            <h2 className="text-3xl font-extrabold">{hasPhysicalItems ? 'Delivery Details' : 'Contact Details'}</h2>
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-bold">Phone Number {hasPhysicalItems && '*'}</label>
                  <input type="text" value={phone} onChange={e => setPhone(e.target.value)} className="w-full h-12 px-4 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800" placeholder="98XXXXXXXX" />
                </div>
                {hasPhysicalItems && (
                <div>
                  <label className="text-sm font-bold">Full Address *</label>
                  <input type="text" value={address} onChange={e => setAddress(e.target.value)} className="w-full h-12 px-4 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800" placeholder="House no, Street, City" />
                </div>
                )}
                <div>
                  <label className="text-sm font-bold">Notes (Optional)</label>
                  <textarea value={notes} onChange={e => setNotes(e.target.value)} className="w-full h-24 p-4 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800" placeholder="Special delivery instructions"></textarea>
                </div>
              </div>
              <Button 
                onClick={handleContinueToPayment} 
                disabled={processingOrder} 
                aria-busy={processingOrder}
                className="w-full sm:w-auto h-14 px-10 font-bold bg-[#163E6B] hover:bg-[#163E6B]/90 text-white"
              >
                {processingOrder ? (
                  <ButtonSpinner text="Creating Order..." />
                ) : (
                  <>
                    Continue to Payment <ArrowRight className="w-5 h-5 ml-2" />
                  </>
                )}
              </Button>
            </div>
            <div>{renderOrderSummary()}</div>
          </div>
        )}

        {step === 2 && (
          <div className="grid grid-cols-1 lg:grid-cols-[1.5fr_1fr] gap-12">
            <div className="space-y-8">
              <h2 className="text-3xl font-extrabold">Payment Verification</h2>
              <div className="bg-[#163E6B]/5 dark:bg-[#D4A72C]/5 border border-[#163E6B]/20 rounded-xl p-6 flex justify-between items-center">
                <div>
                  <p className="font-bold">Amount To Pay</p>
                  <p className="text-xs text-slate-500">Please pay exactly this amount.</p>
                </div>
                <div className="text-2xl font-black text-[#163E6B] dark:text-[#D4A72C]">Rs. {totalAmount}</div>
              </div>

              {/* Payment Methods Selection */}
              <div className="space-y-4">
                <label className="text-sm font-bold">Select Payment Method</label>
                {paymentMethods.length === 0 ? (
                  <p className="text-sm text-red-500">No payment methods available. Please contact support.</p>
                ) : (
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    {paymentMethods.map(method => (
                      <button
                        key={method.id}
                        onClick={() => setSelectedMethodId(method.id)}
                        className={`p-4 rounded-xl border text-center transition-all ${selectedMethodId === method.id ? 'border-[#163E6B] bg-[#163E6B]/5 ring-2 ring-[#163E6B] dark:border-[#D4A72C] dark:bg-[#D4A72C]/10 dark:ring-[#D4A72C]' : 'border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 hover:bg-slate-50 dark:hover:bg-white/10'}`}
                      >
                        <p className="font-bold text-sm">{method.display_name}</p>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Selected Method Details */}
              {selectedMethodId && paymentMethods.find(m => m.id === selectedMethodId) && (
                <div className="bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 rounded-2xl p-6 flex flex-col md:flex-row gap-8">
                  {(() => {
                    const m = paymentMethods.find(m => m.id === selectedMethodId)!;
                    return (
                      <>
                        {m.qr_image && (
                          <div className="shrink-0 mx-auto md:mx-0 text-center">
                            <div className="w-40 h-40 bg-white border border-slate-200 rounded-xl p-2 mb-2 overflow-hidden">
                              <img src={m.qr_image} alt={`${m.display_name} QR`} className="w-full h-full object-contain" />
                            </div>
                            <p className="text-xs font-semibold text-slate-500">Scan to Pay</p>
                          </div>
                        )}
                        <div className="flex-1 space-y-3">
                          <h4 className="font-bold border-b border-slate-100 dark:border-white/10 pb-2">Payment Details</h4>
                          {m.account_name && <p className="text-sm"><span className="text-slate-500">Account Name:</span> <span className="font-semibold">{m.account_name}</span></p>}
                          {m.account_number && <p className="text-sm"><span className="text-slate-500">Account No / ID:</span> <span className="font-semibold">{m.account_number}</span></p>}
                          {m.bank_name && <p className="text-sm"><span className="text-slate-500">Bank:</span> <span className="font-semibold">{m.bank_name}</span></p>}
                          {m.branch && <p className="text-sm"><span className="text-slate-500">Branch:</span> <span className="font-semibold">{m.branch}</span></p>}
                          {m.instructions && (
                            <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-900 text-blue-800 dark:text-blue-300 rounded-lg text-sm">
                              {m.instructions}
                            </div>
                          )}
                        </div>
                      </>
                    );
                  })()}
                </div>
              )}

              <div className="space-y-4">
                <div>
                  <label className="text-sm font-bold">Transaction / Reference Code *</label>
                  <input type="text" value={txnCode} onChange={e => setTxnCode(e.target.value)} className="w-full h-12 px-4 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 uppercase" placeholder="Enter code" />
                </div>
                <div>
                  <label className="text-sm font-bold">Payment Screenshot *</label>
                  <input type="file" accept=".jpg,.jpeg,.png" ref={fileInputRef} className="hidden" onChange={e => {
                    if (e.target.files && e.target.files[0]) setScreenshot(e.target.files[0]);
                  }} />
                  {!screenshot ? (
                    <div onClick={() => fileInputRef.current?.click()} className="w-full h-40 rounded-xl border-2 border-dashed border-slate-300 flex flex-col items-center justify-center cursor-pointer hover:bg-slate-50 dark:hover:bg-white/5">
                      <UploadCloud className="w-8 h-8 text-slate-400 mb-2" />
                      <p className="font-bold">Upload Screenshot</p>
                    </div>
                  ) : (
                    <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-50 dark:bg-emerald-900/10 flex justify-between items-center">
                      <div className="flex items-center gap-3"><ImageIcon className="w-5 h-5 text-emerald-600" /> <span className="font-bold">{screenshot.name}</span></div>
                      <button onClick={() => setScreenshot(null)}><X className="w-5 h-5 text-slate-500" /></button>
                    </div>
                  )}
                </div>
              </div>

              <Button 
                onClick={handlePlaceOrder} 
                disabled={submittingPayment} 
                aria-busy={submittingPayment}
                className="w-full sm:w-auto h-14 px-10 font-bold bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118]"
              >
                {submittingPayment ? (
                  <ButtonSpinner text="Verifying &amp; Submitting Payment..." />
                ) : (
                  "Confirm & Submit Payment"
                )}
              </Button>
            </div>
            <div className="hidden lg:block">{renderOrderSummary()}</div>
          </div>
        )}

        {step === 3 && createdOrder && (
          <div className="max-w-2xl mx-auto text-center py-12">
            <div className="w-24 h-24 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center mx-auto mb-8">
              <CheckCircle2 className="w-12 h-12 text-emerald-600" />
            </div>
            <h2 className="text-3xl font-extrabold mb-4">Order Submitted Successfully</h2>
            <p className="text-lg text-slate-600 mb-8">Your order has been received and your payment is pending verification.</p>
            <div className="bg-white dark:bg-white/5 border border-slate-200 rounded-2xl p-8 text-left mb-10 grid grid-cols-2 gap-8">
              <div><p className="text-sm font-semibold text-slate-500">Order ID</p><p className="text-lg font-bold">#ORD-{createdOrder.id}</p></div>
              <div><p className="text-sm font-semibold text-slate-500">Total Amount</p><p className="text-lg font-bold">Rs. {createdOrder.total_amount}</p></div>
              <div><p className="text-sm font-semibold text-slate-500">Status</p><p className="text-lg font-bold text-yellow-600">Pending Verification</p></div>
              <div><p className="text-sm font-semibold text-slate-500">Transaction Ref</p><p className="text-lg font-bold uppercase">{txnCode}</p></div>
            </div>
            <Button onClick={() => router.push("/student/marketplace/orders")} className="h-12 px-8 font-bold bg-[#163E6B] text-white">View My Orders</Button>
          </div>
        )}
      </main>
    </div>
  );
}
