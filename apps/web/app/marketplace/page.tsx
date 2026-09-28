"use client";

import React, { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Search, ShoppingBag, Book, FileText, PenTool, Layers, BookOpen,
  Brain, FileQuestion, ChevronRight, SlidersHorizontal, Lock,
  Heart, ShoppingCart, Star, Plus, Minus, CreditCard, ShieldCheck,
  Truck, ArrowRight, BookMarked, CheckCircle2, Video, Loader2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { publicApi, type PublicProduct } from "@/lib/api/public-api";

type ProductType = "Physical" | "Digital";

interface Product {
  id: string;
  name: string;
  description: string;
  category: string;
  exam: string;
  type: ProductType;
  price: number;
  originalPrice?: number;
  discountPercentage?: number;
  stock: number;
  rating: number;
  reviews: number;
  isFeatured: boolean;
  isBestSeller: boolean;
  isNewArrival: boolean;
  imageColor: string;
  coverImage: string | null;
  condition?: string | null;
  stockStatus: string;
  sellerName?: string | null;
  // S2S fields
  isSellerListing?: boolean;
  conditionDisplay?: string | null;
  sellerLocation?: string | null;
}


const CATEGORY_ICONS: Record<string, any> = {
  "PDF": FileText,
  "Study Material": Book,
  "Question Collection": FileQuestion,
  "Question Set": Layers,
  "Video": Video,
  "Course": BookOpen,
  "Bundle": Layers,
};

const IMAGE_GRADIENTS = [
  "from-[#163E6B] to-[#0A1118]",
  "from-[#D4A72C] to-[#8C6D1D]",
  "from-emerald-700 to-emerald-900",
  "from-slate-700 to-slate-900",
  "from-blue-700 to-blue-900",
  "from-purple-700 to-purple-900",
];

function mapProduct(p: PublicProduct, idx: number): Product {
  const price = parseFloat(p.final_price);
  const original = p.discount_price !== null ? parseFloat(p.price) : undefined;
  const discountPercentage = original && original > price
    ? Math.round(((original - price) / original) * 100)
    : undefined;
  return {
    id: String(p.id),
    name: p.title,
    description: p.description,
    category: p.category_display,
    exam: p.target_exam_name || "General",
    type: p.category === "COURSE" ? "Digital" : "Physical",
    price,
    originalPrice: original,
    discountPercentage,
    stock: p.stock ?? 0,
    stockStatus: p.stock !== undefined ? (p.stock > 0 ? `${p.stock} in stock` : "Out of Stock") : "In Stock",
    rating: 0,
    reviews: 0,
    isSellerListing: (p as any).is_seller_listing ?? false,
    conditionDisplay: (p as any).condition_display ?? null,
    sellerLocation: (p as any).location ?? null,
    isFeatured: idx < 4,
    isBestSeller: false,
    isNewArrival: false,
    imageColor: IMAGE_GRADIENTS[idx % IMAGE_GRADIENTS.length] as string,
    coverImage: p.cover_image,
    condition: p.condition,
    sellerName: p.seller_details ? p.seller_details.first_name + (p.seller_details as any).last_name ? ` ${(p.seller_details as any).last_name}` : "" : null,
  };
}

export default function MarketplacePage() {
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedCategory, setSelectedCategory] = useState<string>("All");
  const [selectedExam, setSelectedExam] = useState<string>("All Exams");
  const [selectedPrice, setSelectedPrice] = useState<string>("All Prices");
  const [selectedSellerType, setSelectedSellerType] = useState<string>("All");
  const [sortBy, setSortBy] = useState<string>("Recommended");
  const [products, setProducts] = useState<Product[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Modals state
  const [showWishlistPrompt, setShowWishlistPrompt] = useState(false);
  const [cartItems, setCartItems] = useState<{product: Product, quantity: number}[]>([]);
  const [showCart, setShowCart] = useState(false);
  const [isCheckoutOpen, setIsCheckoutOpen] = useState(false);

  useEffect(() => {
    let mounted = true;
    publicApi.getProducts(24).then((data) => {
      if (!mounted) return;
      setProducts((data || []).map(mapProduct));
      setIsLoading(false);
    });
    return () => { mounted = false; };
  }, []);

  const CATEGORIES = useMemo(() => Array.from(new Set(products.map(p => p.category))), [products]);
  const EXAMS = useMemo(() => ["All Exams", ...Array.from(new Set(products.map(p => p.exam)))], [products]);

  // Filter logic
  const filteredProducts = products.filter(product => {
    const matchesSearch = product.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          product.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = selectedCategory === "All" || product.category === selectedCategory;
    const matchesExam = selectedExam === "All Exams" || product.exam === selectedExam;

    let matchesPrice = true;
    if (selectedPrice === "Under Rs. 500") matchesPrice = product.price < 500;
    if (selectedPrice === "Rs. 500-1,000") matchesPrice = product.price >= 500 && product.price <= 1000;
    if (selectedPrice === "Rs. 1,000-2,000") matchesPrice = product.price > 1000 && product.price <= 2000;
    if (selectedPrice === "Rs. 2,000+") matchesPrice = product.price > 2000;

    let matchesSellerType = true;
    if (selectedSellerType === "Student Sellers") matchesSellerType = !!(product as any).isSellerListing;
    if (selectedSellerType === "Platform") matchesSellerType = !(product as any).isSellerListing;

    return matchesSearch && matchesCategory && matchesExam && matchesPrice && matchesSellerType;
  }).sort((a, b) => {
    if (sortBy === "Price: Low to High") return a.price - b.price;
    if (sortBy === "Price: High to Low") return b.price - a.price;
    return 0;
  });

    const router = useRouter();
  const handleAddToCart = (product: Product, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    router.push(`/marketplace/product/${product.id}`);
  };

  const handleWishlist = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowWishlistPrompt(true);
  };

  const updateQuantity = (id: string, delta: number) => {
    setCartItems(prev => prev.map(item => {
      if (item.product.id === id) {
        const newQuantity = Math.max(0, item.quantity + delta);
        return { ...item, quantity: newQuantity };
      }
      return item;
    }).filter(item => item.quantity > 0));
  };

  const cartTotal = cartItems.reduce((sum, item) => sum + (item.product.price * item.quantity), 0);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-[#0A1118] text-slate-900 dark:text-slate-50 flex flex-col font-sans selection:bg-[#163E6B]/20 dark:selection:bg-[#D4A72C]/30">
      <main className="flex-1">
          {/* 1. HERO SECTION */}
          <section className="relative pt-32 pb-20 overflow-hidden bg-[#0A1118] border-b border-white/10">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,#163E6B_0%,transparent_70%)] opacity-30"></div>
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff0a_1px,transparent_1px),linear-gradient(to_bottom,#ffffff0a_1px,transparent_1px)] bg-[size:24px_24px]"></div>
          
          <div className="container mx-auto px-4 relative z-10 text-center max-w-4xl">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/5 border border-white/10 backdrop-blur-md mb-8">
              <ShoppingBag className="w-4 h-4 text-[#D4A72C]" />
              <span className="text-[11px] font-bold uppercase tracking-widest text-white/90">
                LOKSEWA STUDY MARKETPLACE
              </span>
            </div>
            
            <h1 className="text-4xl md:text-6xl font-[900] text-white tracking-tight mb-6 leading-[1.1]">
              Everything You Need For <br className="hidden md:block"/>
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-white to-white/70">Your Preparation.</span>
            </h1>
            
            <p className="text-lg md:text-xl text-slate-300 font-[500] max-w-2xl mx-auto mb-12">
              Discover books, study materials, stationery, and carefully selected preparation resources built for serious Loksewa aspirants.
            </p>

            <div className="relative max-w-2xl mx-auto mb-8 group">
              <div className="absolute inset-y-0 left-5 flex items-center pointer-events-none">
                <Search className="h-5 w-5 text-slate-400 group-focus-within:text-[#D4A72C] transition-colors" />
              </div>
              <input
                type="text"
                className="w-full h-16 pl-14 pr-32 rounded-[16px] bg-white/10 border border-white/20 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-[#D4A72C]/50 focus:bg-white/15 backdrop-blur-md text-lg font-[500] transition-all"
                placeholder="Search books, notes, stationery..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <div className="absolute inset-y-0 right-3 flex items-center gap-2">
                <div className="hidden sm:flex items-center gap-1 px-2 py-1 rounded bg-white/10 border border-white/10 text-xs text-slate-300 font-mono">
                  <span>⌘</span><span>K</span>
                </div>
                <Button className="h-10 px-5 rounded-[10px] bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] font-[700]">
                  Search
                </Button>
              </div>
            </div>

            <div className="flex flex-wrap justify-center gap-3">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  onClick={() => {
                    setSelectedCategory(cat);
                    document.getElementById('marketplace-grid')?.scrollIntoView({ behavior: 'smooth' });
                  }}
                  className="px-4 py-2 rounded-full bg-white/5 hover:bg-white/10 border border-white/10 text-white text-sm font-[600] transition-colors"
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* 2. CATEGORY NAVIGATION */}
        {CATEGORIES.length > 0 && (
        <section className="py-16 bg-white dark:bg-[#060B11] border-b border-slate-200 dark:border-white/5">
          <div className="container mx-auto px-4 max-w-7xl">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              {CATEGORIES.map((cat, idx) => {
                const Icon = CATEGORY_ICONS[cat] || Book;
                return (
                <div
                  key={idx}
                  onClick={() => {
                    setSelectedCategory(cat);
                    document.getElementById('marketplace-grid')?.scrollIntoView({ behavior: 'smooth' });
                  }}
                  className="group flex flex-col items-center text-center p-6 rounded-[20px] bg-slate-50 dark:bg-white/5 border border-slate-200 dark:border-white/10 hover:border-[#163E6B]/30 dark:hover:border-white/30 hover:bg-white dark:hover:bg-white/10 transition-all cursor-pointer shadow-sm hover:shadow-md"
                >
                  <div className="w-12 h-12 rounded-full bg-[#163E6B]/5 dark:bg-white/5 flex items-center justify-center mb-4 group-hover:bg-[#163E6B] dark:group-hover:bg-[#D4A72C] transition-colors">
                    <Icon className="w-5 h-5 text-[#163E6B] dark:text-[#D4A72C] group-hover:text-white dark:group-hover:text-[#0A1118] transition-colors" />
                  </div>
                  <h3 className="text-sm font-[800] text-slate-900 dark:text-white mb-1 leading-tight">{cat}</h3>
                </div>
                );
              })}
            </div>
          </div>
        </section>
        )}

        {/* 3. FEATURED BANNER */}
        <section className="py-16 bg-white dark:bg-[#060B11]">
          <div className="container mx-auto px-4 max-w-7xl">
            <div className="relative rounded-[24px] overflow-hidden bg-gradient-to-r from-[#163E6B] to-[#0A1118] border border-slate-200 dark:border-white/10 shadow-2xl">
              <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] opacity-10"></div>
              <div className="relative z-10 flex flex-col md:flex-row items-center justify-between p-8 md:p-16 gap-8">
                <div className="text-left text-white max-w-xl">
                  <div className="inline-block px-3 py-1 bg-white/10 rounded-full border border-white/20 text-xs font-[700] tracking-wider uppercase mb-4">
                    Exclusive Collection
                  </div>
                  <h2 className="text-3xl md:text-5xl font-[900] tracking-tight mb-4">Prepare Better.<br/>Study Smarter.</h2>
                  <p className="text-lg text-white/80 font-[500] mb-8">Curated resources, premium books, and comprehensive study materials designed exclusively for your Loksewa journey.</p>
                  <Button className="h-12 px-8 rounded-[12px] bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] font-[700]">
                    Explore Collection <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </div>
                <div className="hidden md:flex flex-col gap-4 items-center">
                  {/* Decorative elements representing study desk */}
                  <div className="flex gap-4">
                    <div className="w-32 h-40 bg-white/10 rounded-[12px] border border-white/20 backdrop-blur-sm shadow-xl flex items-center justify-center -rotate-6">
                      <Book className="w-10 h-10 text-[#D4A72C] opacity-80" />
                    </div>
                    <div className="w-32 h-40 bg-white/10 rounded-[12px] border border-white/20 backdrop-blur-sm shadow-xl flex items-center justify-center rotate-6 mt-8">
                      <FileText className="w-10 h-10 text-[#D4A72C] opacity-80" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 4 & 5. MARKETPLACE MAIN LAYOUT (Filters + Grid) */}
        <section id="marketplace-grid" className="py-16 bg-slate-50 dark:bg-[#0A1118] border-t border-slate-200 dark:border-white/5">
          <div className="container mx-auto px-4 max-w-7xl">
            
            <div className="flex flex-col lg:flex-row gap-8">
              
              {/* Sidebar Filters */}
              <div className="w-full lg:w-64 shrink-0 space-y-8">
                <div>
                  <div className="flex items-center gap-2 mb-4">
                    <SlidersHorizontal className="w-5 h-5 text-slate-500" />
                    <h3 className="text-lg font-[800] text-slate-900 dark:text-white">Filters</h3>
                  </div>
                  <Button 
                    variant="ghost" 
                    className="w-full justify-start h-8 px-2 text-xs font-[600] text-slate-500 hover:text-slate-900 dark:hover:text-white mb-4"
                    onClick={() => {
                      setSearchQuery("");
                      setSelectedCategory("All");
                      setSelectedExam("All Exams");
                      setSelectedPrice("All Prices");
                      setSelectedSellerType("All");
                      setSortBy("Recommended");
                    }}
                  >
                    Clear All Filters
                  </Button>
                </div>

                {/* Category Filter */}
                <div>
                  <h4 className="text-sm font-[700] text-slate-900 dark:text-white mb-3">Category</h4>
                  <div className="space-y-2">
                    {["All", ...CATEGORIES].map(cat => (
                      <label key={cat} className="flex items-center gap-3 cursor-pointer group">
                        <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${
                          selectedCategory === cat 
                            ? 'bg-[#163E6B] border-[#163E6B] dark:bg-[#D4A72C] dark:border-[#D4A72C]' 
                            : 'border-slate-300 dark:border-white/20 group-hover:border-[#163E6B] dark:group-hover:border-white/40'
                        }`}>
                          {selectedCategory === cat && <CheckCircle2 className="w-3 h-3 text-white dark:text-[#0A1118]" />}
                        </div>
                        <span className={`text-sm font-[500] ${selectedCategory === cat ? 'text-slate-900 dark:text-white font-[700]' : 'text-slate-600 dark:text-slate-400'}`}>
                          {cat}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Exam Filter */}
                <div>
                  <h4 className="text-sm font-[700] text-slate-900 dark:text-white mb-3">Target Exam</h4>
                  <div className="space-y-2">
                    {EXAMS.map(exam => (
                      <label key={exam} className="flex items-center gap-3 cursor-pointer group">
                        <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${
                          selectedExam === exam 
                            ? 'bg-[#163E6B] border-[#163E6B] dark:bg-[#D4A72C] dark:border-[#D4A72C]' 
                            : 'border-slate-300 dark:border-white/20 group-hover:border-[#163E6B] dark:group-hover:border-white/40'
                        }`}>
                          {selectedExam === exam && <CheckCircle2 className="w-3 h-3 text-white dark:text-[#0A1118]" />}
                        </div>
                        <span className={`text-sm font-[500] ${selectedExam === exam ? 'text-slate-900 dark:text-white font-[700]' : 'text-slate-600 dark:text-slate-400'}`}>
                          {exam}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Price Filter */}
                <div>
                  <h4 className="text-sm font-[700] text-slate-900 dark:text-white mb-3">Price</h4>
                  <div className="space-y-2">
                    {["All Prices", "Under Rs. 500", "Rs. 500-1,000", "Rs. 1,000-2,000", "Rs. 2,000+"].map(price => (
                      <label key={price} className="flex items-center gap-3 cursor-pointer group">
                        <div className={`w-4 h-4 rounded-full border flex items-center justify-center transition-colors ${
                          selectedPrice === price 
                            ? 'bg-[#163E6B] border-[#163E6B] dark:bg-[#D4A72C] dark:border-[#D4A72C]' 
                            : 'border-slate-300 dark:border-white/20 group-hover:border-[#163E6B] dark:group-hover:border-white/40'
                        }`}>
                          {selectedPrice === price && <div className="w-1.5 h-1.5 rounded-full bg-white dark:bg-[#0A1118]" />}
                        </div>
                        <span className={`text-sm font-[500] ${selectedPrice === price ? 'text-slate-900 dark:text-white font-[700]' : 'text-slate-600 dark:text-slate-400'}`}>
                          {price}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Seller Type Filter */}
                <div>
                  <h4 className="text-sm font-[700] text-slate-900 dark:text-white mb-3">Seller Type</h4>
                  <div className="space-y-2">
                    {["All", "Student Sellers", "Platform"].map(type => (
                      <label key={type} className="flex items-center gap-3 cursor-pointer group">
                        <div className={`w-4 h-4 rounded-full border flex items-center justify-center transition-colors ${
                          selectedSellerType === type 
                            ? 'bg-[#163E6B] border-[#163E6B] dark:bg-[#D4A72C] dark:border-[#D4A72C]' 
                            : 'border-slate-300 dark:border-white/20 group-hover:border-[#163E6B] dark:group-hover:border-white/40'
                        }`}>
                          {selectedSellerType === type && <div className="w-1.5 h-1.5 rounded-full bg-white dark:bg-[#0A1118]" />}
                        </div>
                        <span className={`text-sm font-[500] ${selectedSellerType === type ? 'text-slate-900 dark:text-white font-[700]' : 'text-slate-600 dark:text-slate-400'}`}>
                          {type}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

              </div>

              {/* Main Library Grid */}
              <div className="flex-1">
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
                  <div>
                    <h2 className="text-2xl font-[800] text-slate-900 dark:text-white">Shop Resources</h2>
                    <p className="text-sm text-slate-500 font-[500] mt-1">Showing {filteredProducts.length} results</p>
                  </div>
                  
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-[600] text-slate-500">Sort by:</span>
                    <select 
                      className="h-10 px-3 rounded-[10px] bg-white dark:bg-white/5 border border-slate-200 dark:border-white/10 text-sm font-[600] text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-[#163E6B]/20 dark:focus:ring-white/20"
                      value={sortBy}
                      onChange={(e) => setSortBy(e.target.value)}
                    >
                      {["Recommended", "Price: Low to High", "Price: High to Low"].map(o => (
                        <option key={o} value={o}>{o}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {isLoading ? (
                  <div className="flex items-center justify-center py-20">
                    <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
                  </div>
                ) : filteredProducts.length > 0 ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                    {filteredProducts.map(product => (
                      <div
                        key={product.id}
                        className="group flex flex-col bg-white dark:bg-[#060B11] border border-slate-200 dark:border-white/10 rounded-[20px] overflow-hidden hover:shadow-xl hover:border-[#163E6B]/30 dark:hover:border-white/30 transition-all cursor-pointer h-full"
                        onClick={() => router.push(`/marketplace/product/${product.id}`)}
                      >
                        {/* Product Image Area */}
                        <div className={`relative h-48 w-full ${product.coverImage ? "" : `bg-gradient-to-br ${product.imageColor}`}`}>
                          {product.coverImage ? (
                            <img src={product.coverImage} alt={product.name} className="absolute inset-0 w-full h-full object-cover" />
                          ) : (
                            <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff1a_1px,transparent_1px),linear-gradient(to_bottom,#ffffff1a_1px,transparent_1px)] bg-[size:12px_12px]"></div>
                          )}

                          {/* Wishlist Button */}
                          <button
                            className="absolute top-3 right-3 w-8 h-8 rounded-full bg-white/10 backdrop-blur-sm border border-white/20 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-white/20"
                            onClick={handleWishlist}
                          >
                            <Heart className="w-4 h-4 text-white" />
                          </button>
                        </div>

                        {/* Product Details */}
                        <div className="p-5 flex flex-col flex-1">
                          {/* Category + Seller type badges */}
                          <div className="flex flex-wrap gap-1.5 mb-2">
                            <div className="text-[10px] font-[800] uppercase tracking-wider text-[#163E6B] dark:text-[#D4A72C]">
                              {product.category}
                            </div>
                            {(product as any).isSellerListing && (
                              <span className="text-[9px] font-[800] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
                                Student Seller
                              </span>
                            )}
                            {(product as any).conditionDisplay && (
                              <span className="text-[9px] font-[700] px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300">
                                {(product as any).conditionDisplay}
                              </span>
                            )}
                          </div>

                          <h3 className="text-sm font-[800] text-slate-900 dark:text-white leading-tight mb-2 line-clamp-2 flex-1 group-hover:text-[#163E6B] dark:group-hover:text-[#D4A72C] transition-colors">
                            {product.name}
                          </h3>

                          {/* Seller location for used books */}
                          {(product as any).sellerLocation && (
                            <p className="text-[10px] text-slate-400 mb-1 flex items-center gap-1">
                              <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                              {(product as any).sellerLocation}
                            </p>
                          )}

                          <div className="flex items-end justify-between mt-auto pt-4 border-t border-slate-100 dark:border-white/5">
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="text-lg font-[800] text-slate-900 dark:text-white">Rs. {product.price}</span>
                                {product.originalPrice && (
                                  <span className="text-xs font-[500] text-slate-400 line-through">Rs. {product.originalPrice}</span>
                                )}
                              </div>
                              {product.discountPercentage && (
                                <div className="text-[10px] font-[700] text-emerald-600 dark:text-emerald-400">
                                  {product.discountPercentage}% OFF
                                </div>
                              )}
                            </div>
                            {product.stockStatus === "Out of Stock" && (
                              <span className="text-[10px] font-[700] text-red-500">Out of Stock</span>
                            )}
                          </div>
                        </div>

                                                {/* Add to Cart Footer */}
                        <div className="px-5 pb-5">
                          <Button 
                            className="w-full h-10 rounded-[10px] bg-slate-100 hover:bg-[#163E6B] text-slate-900 hover:text-white font-[700] dark:bg-white/5 dark:hover:bg-white dark:text-white dark:hover:text-[#0A1118] transition-all disabled:opacity-50 disabled:hover:bg-slate-100 dark:disabled:hover:bg-white/5 disabled:hover:text-slate-900 dark:disabled:hover:text-white"
                            onClick={(e) => handleAddToCart(product, e)}
                            disabled={product.stock === 0}
                          >
                            <ShoppingCart className="w-4 h-4 mr-2" /> {product.stock === 0 ? "Out of Stock" : "Add to Cart"}
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="bg-white dark:bg-[#060B11] border border-slate-200 dark:border-white/10 rounded-[24px] p-12 text-center flex flex-col items-center justify-center min-h-[400px]">
                    <div className="w-16 h-16 rounded-full bg-slate-50 dark:bg-white/5 flex items-center justify-center mb-6">
                      <Search className="w-8 h-8 text-slate-300 dark:text-white/20" />
                    </div>
                    <h3 className="text-xl font-[800] text-slate-900 dark:text-white mb-2">No products found</h3>
                    <p className="text-slate-500 font-[500] max-w-md mx-auto mb-8">
                      Try adjusting your search query, or clear your filters to see more results in the marketplace.
                    </p>
                    <Button 
                      variant="outline" 
                      onClick={() => {
                        setSearchQuery("");
                        setSelectedCategory("All");
                        setSelectedExam("All Exams");
                        setSelectedPrice("All Prices");
                      }}
                      className="font-[700]"
                    >
                      Clear All Filters
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>

        {/* 6. TRUST SECTION */}
        <section className="py-16 bg-white dark:bg-[#060B11] border-t border-slate-200 dark:border-white/5">
          <div className="container mx-auto px-4 max-w-7xl">
            <div className="text-center mb-12">
              <h2 className="text-2xl font-[800] text-slate-900 dark:text-white tracking-tight">Shop With Confidence</h2>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              {[
                { icon: ShieldCheck, title: "Quality Resources", desc: "Carefully selected study materials." },
                { icon: CreditCard, title: "Secure Checkout", desc: "Protected shopping experience." },
                { icon: FileText, title: "Verified Products", desc: "Accurate product information." },
                { icon: Brain, title: "Student Focused", desc: "Selected specifically for preparation." }
              ].map((item, i) => (
                <div key={i} className="flex flex-col items-center text-center p-6 bg-slate-50 dark:bg-[#0A1118] rounded-[20px] border border-slate-200 dark:border-white/5">
                  <div className="w-12 h-12 rounded-full bg-[#163E6B]/10 dark:bg-[#D4A72C]/10 flex items-center justify-center mb-4">
                    <item.icon className="w-5 h-5 text-[#163E6B] dark:text-[#D4A72C]" />
                  </div>
                  <h4 className="text-sm font-[800] text-slate-900 dark:text-white mb-2">{item.title}</h4>
                  <p className="text-xs text-slate-500 font-[500]">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* 7. PREMIUM CTA */}
        <section className="py-24 relative overflow-hidden bg-[#163E6B] dark:bg-transparent dark:border-t dark:border-white/10">
          <div className="absolute inset-0 z-0 pointer-events-none hidden dark:block">
            <div className="absolute inset-0 bg-gradient-to-b from-[#0A1118] to-[#060B11]"></div>
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom,#D4A72C_0%,transparent_60%)] opacity-10"></div>
          </div>
          
          <div className="container mx-auto px-4 relative z-10 text-center max-w-3xl">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/10 border border-white/20 backdrop-blur-md mb-6 shadow-sm">
              <span className="text-[10px] font-bold uppercase tracking-widest text-white dark:text-[#D4A72C]">
                PREPARE WITH THE RIGHT TOOLS
              </span>
            </div>
            <h2 className="text-3xl md:text-5xl font-[900] text-white tracking-tight mb-6 leading-tight">
              Build Your Perfect Study Kit.
            </h2>
            <p className="text-lg md:text-xl text-white/80 font-[500] mb-10 leading-relaxed max-w-2xl mx-auto">
              Choose the resources that match your target exam, preparation style, and study goals.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Button 
                className="w-full sm:w-auto h-14 px-8 rounded-[12px] bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] font-[800] text-[16px] shadow-[0_0_20px_rgba(212,167,44,0.3)]"
                onClick={() => {
                  setSelectedCategory("All");
                  document.getElementById('marketplace-grid')?.scrollIntoView({ behavior: 'smooth' });
                }}
              >
                Explore Products <ArrowRight className="w-5 h-5 ml-2" />
              </Button>
              <Button 
                variant="outline" 
                className="w-full sm:w-auto h-14 px-8 rounded-[12px] border-white/20 bg-white/5 hover:bg-white/10 text-white font-[700] text-[16px] backdrop-blur-sm"
                onClick={() => {
                  setSelectedCategory("Preparation Bundles");
                  document.getElementById('marketplace-grid')?.scrollIntoView({ behavior: 'smooth' });
                }}
              >
                View Bundles
              </Button>
            </div>
          </div>
        </section>

      </main>

      {/* PRODUCT PREVIEW DIALOG */}
      

      {/* CART DRAWER SIMULATION */}
      {showCart && (
        <>
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 transition-opacity" onClick={() => setShowCart(false)}></div>
          <div className="fixed inset-y-0 right-0 w-full max-w-md bg-white dark:bg-[#0A1118] border-l border-slate-200 dark:border-white/10 shadow-2xl z-50 flex flex-col transform transition-transform duration-300">
            <div className="p-6 border-b border-slate-100 dark:border-white/5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <ShoppingCart className="w-6 h-6 text-[#163E6B] dark:text-white" />
                <h2 className="text-xl font-[800] text-slate-900 dark:text-white">Your Cart</h2>
                <span className="px-2 py-1 bg-slate-100 dark:bg-white/10 text-slate-600 dark:text-slate-300 text-xs font-[700] rounded-full">
                  {cartItems.reduce((sum, item) => sum + item.quantity, 0)}
                </span>
              </div>
              <button className="text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors" onClick={() => setShowCart(false)}>
                ✕
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-4">
              {cartItems.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center opacity-50">
                  <ShoppingCart className="w-16 h-16 mb-4 text-slate-300 dark:text-white/20" />
                  <p className="text-lg font-[700]">Your cart is empty</p>
                </div>
              ) : (
                cartItems.map((item) => (
                  <div key={item.product.id} className="flex gap-4 p-4 rounded-[16px] border border-slate-100 dark:border-white/5 bg-slate-50 dark:bg-white/5">
                    <div className={`w-20 h-24 rounded-[10px] shrink-0 bg-gradient-to-br ${item.product.imageColor}`}></div>
                    <div className="flex-1 flex flex-col">
                      <h4 className="text-sm font-[700] text-slate-900 dark:text-white leading-tight mb-1 line-clamp-2">
                        {item.product.name}
                      </h4>
                      <p className="text-xs text-slate-500 font-[500] mb-2">{item.product.category}</p>
                      <div className="mt-auto flex items-center justify-between">
                        <span className="text-sm font-[800] text-slate-900 dark:text-white">Rs. {item.product.price}</span>
                        <div className="flex items-center gap-3 bg-white dark:bg-[#0A1118] border border-slate-200 dark:border-white/10 rounded-full px-2 py-1 shadow-sm">
                          <button onClick={() => updateQuantity(item.product.id, -1)} className="w-5 h-5 flex items-center justify-center text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors">
                            <Minus className="w-3 h-3" />
                          </button>
                          <span className="text-xs font-[700] w-4 text-center">{item.quantity}</span>
                          <button onClick={() => updateQuantity(item.product.id, 1)} className="w-5 h-5 flex items-center justify-center text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors">
                            <Plus className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            {cartItems.length > 0 && (
              <div className="p-6 border-t border-slate-100 dark:border-white/5 bg-slate-50 dark:bg-white/5">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm font-[600] text-slate-500">Subtotal</span>
                  <span className="text-lg font-[800] text-slate-900 dark:text-white">Rs. {cartTotal}</span>
                </div>
                <div className="flex justify-between items-center mb-6">
                  <span className="text-sm font-[600] text-slate-500">Delivery</span>
                  <span className="text-xs font-[500] text-slate-400">Calculated at checkout</span>
                </div>
                <Button 
                  className="w-full h-14 rounded-[12px] bg-[#163E6B] hover:bg-[#163E6B]/90 text-white font-[800] text-[16px] dark:bg-white dark:hover:bg-slate-200 dark:text-[#0A1118] mb-3"
                  onClick={() => { setShowCart(false); setIsCheckoutOpen(true); }}
                >
                  Proceed to Checkout <ArrowRight className="w-5 h-5 ml-2" />
                </Button>
                <Button variant="ghost" className="w-full font-[600] text-slate-500 hover:text-slate-900 dark:hover:text-white" onClick={() => setShowCart(false)}>
                  Continue Shopping
                </Button>
              </div>
            )}
          </div>
        </>
      )}

      {/* WISHLIST PROMPT */}
      

    </div>
  );
}
