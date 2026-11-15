// Screen text in English and Chinese, like the kiosk (kiosk-app/src/i18n.js). The app starts in the
// phone's language when that's Chinese, and remembers the customer's own pick.
// Drink, ingredient and shop names from the backend stay as the backend sends them.
//
// t('key', { name: 'x' }) fills {name}; a `count` var picks 'key_one' when count is 1.
import AsyncStorage from '@react-native-async-storage/async-storage';
import { getLocales } from 'expo-localization';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export type Lang = 'en' | 'zh';
export const LANGUAGES: { code: Lang; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'zh', label: '中文' },
];

const en = {
  'tab.menu': 'Menu',
  'tab.order': 'Order',
  'title.order': 'Your order',
  'title.designer': 'Design your own',
  'title.shops': 'Choose a shop',
  'title.payment': 'Your order',

  'cat.Milk Tea': 'Milk Tea',
  'cat.Fruit Tea': 'Fruit Tea',
  'cat.Smoothie': 'Smoothie',
  'cat.Coffee': 'Coffee',
  'cat.Others': 'Others',
  'menu.all': 'All',
  'menu.pickUpAt': 'Pick up at',
  'menu.change': 'Change',
  'menu.design': 'Design your own',
  'menu.designHint': 'Choose your tea, milk and toppings',
  'menu.empty': 'Nothing here right now. Try another section.',
  'menu.loading': 'Loading the menu…',
  'menu.offline': "Can't reach the shop right now.",
  'menu.retry': 'Try again',
  'menu.activeOrder': 'Order {id} · {status}',
  'menu.order': 'Order {id}',
  'menu.activeHint': 'Tap for your pickup code',
  'menu.language': 'Language',

  'shops.title': 'Where will you pick up?',
  'shops.none': 'No shops are open right now.',
  'shops.error': "Couldn't load the shops.",

  'drink.size': 'Size',
  'drink.regular': 'Regular',
  'drink.large': 'Large',
  'drink.sugar': 'Sugar',
  'drink.ice': 'Ice',
  'drink.add': 'Add to order',
  'drink.save': 'Save changes',
  'drink.close': 'Close',
  'drink.from': '{name}, from {price}',
  'nutri.sugar': '{percent}% sugar',

  'bar.review': 'Review order',
  'bar.label': 'Review order, {drinks}, {total}',

  'cart.emptyTitle': 'Your order is empty',
  'cart.emptyText': 'Pick a drink from the menu to get started.',
  'cart.browse': 'Browse the menu',
  'cart.pickUpAt': 'Pick up at {shop}',
  'cart.designed': 'DESIGNED',
  'cart.detail': '{size} · Sugar {sugar} · Ice {ice}',
  'cart.edit': 'Edit',
  'cart.editLabel': 'Edit {name}',
  'cart.remove': 'Remove {name}',
  'cart.less': 'One less {name}',
  'cart.more': 'One more {name}',
  'cart.drinks_one': '{count} drink',
  'cart.drinks': '{count} drinks',
  'cart.placing': 'Placing order…',
  'cart.place': 'Place order',
  'cart.tooMany': 'One order can have up to {max} drinks. Please remove some, or place a second order after this one.',
  'cart.soldOut': 'Sorry, not enough stock for: {names}',
  'cart.busy': 'Lots of orders are coming in from your connection. Please wait a minute, then try again.',
  'cart.offline': "Can't reach the shop right now. Check your connection and try again.",
  'closed.machine_offline': 'This shop is closed right now. Please try again later, or pick another shop.',
  'closed.maintenance': 'This shop is closed for maintenance right now. Please try again later, or pick another shop.',
  'closed.machine_not_ready': "This shop's machine needs a quick refill or check before it can make drinks. Please try again in a little while, or pick another shop.",

  'pay.orderNumber': 'Order number',
  'pay.collectAt': 'Collect at {shop}',
  'pay.cancelled': "This order was cancelled and you haven't been charged.",
  'pay.collected': 'Collected. Enjoy your drink!',
  'pay.step1': '1. Pay with PayNow',
  'pay.paid': 'Paid',
  'pay.testMode': 'Test mode: no real money will be charged',
  'pay.qrAlt': 'PayNow QR code',
  'pay.ref': 'Reference: {ref}',
  'pay.payBy': 'Pay by {time} or the order is cancelled.',
  'pay.hint': 'Take a screenshot of this code, then open your banking app, choose Scan & Pay and pick the screenshot from your gallery.',
  'pay.received': 'Payment of {amount} received. Thank you!',
  'pay.step2': '2. Collect at the machine',
  'pay.codeLater': 'Your code works once the payment comes through.',
  'pay.cancel': 'Cancel order',
  'pay.cancelling': 'Cancelling…',
  'pay.newOrder': 'Start a new order',
  'pay.retry': 'Try again',
  'pay.qrError': "The payment code didn't load.",
  'status.unpaid': 'waiting for payment',
  'status.paid': 'paid',
  'status.PREPARING': 'being made',
  'status.READY': 'ready to collect',
  'progress.PREPARING': 'Your drink is being made.',
  'progress.READY': 'Ready to collect at the machine.',
  'progress.FAILED': "Sorry, the machine couldn't make your drink. Staff have been told.",
  'progress.REFUND_NEEDED': "Sorry, your drink couldn't be made. Your payment is being refunded.",

  'pickup.missing': 'Your pickup code is on the screen you saw right after ordering.',
  'pickup.qr': 'QR code',
  'pickup.pin': 'PIN',
  'pickup.qrAlt': 'Pickup QR code',
  'pickup.qrHint': 'Hold this up to the scanner on the machine.',
  'pickup.pinLabel': 'Pickup PIN {digits}',
  'pickup.pinHint': "Key this PIN in on the machine's screen.",

  'designer.chooseShop': 'Choose a shop first.',
  'designer.loadError': "The drink designer didn't load. Please try again in a moment.",
  'designer.loading': 'Loading…',
  'designer.cupSize': 'Cup size',
  'designer.soldOut': 'Sold out',
  'designer.included': 'Included',
  'designer.sugarIce': 'Sugar and ice',
  'designer.price': 'Price',
  'designer.kioskQr': 'Kiosk QR',
  'designer.chooseLiquid': 'Choose at least one liquid',
  'designer.ownDrink': 'Your own drink',
  'designer.per100': 'Nutri-Grade\n{sugar} g sugar\n{fat} g sat. fat / 100 mL',
  'designer.scanTitle': 'Scan this at the kiosk',
  'designer.scanText': "Hold it up to the kiosk's reader and your drink appears on its screen.",
  'designer.done': 'Done',
};

type Key = keyof typeof en;

const zh: Partial<Record<Key, string>> = {
  'tab.menu': '菜单',
  'tab.order': '订单',
  'title.order': '我的订单',
  'title.designer': '自己调一杯',
  'title.shops': '选择门店',
  'title.payment': '我的订单',

  'cat.Milk Tea': '奶茶',
  'cat.Fruit Tea': '果茶',
  'cat.Smoothie': '冰沙',
  'cat.Coffee': '咖啡',
  'cat.Others': '其他',
  'menu.all': '全部',
  'menu.pickUpAt': '取餐门店',
  'menu.change': '更换',
  'menu.design': '自己调一杯',
  'menu.designHint': '自选茶底、奶和配料',
  'menu.empty': '这里暂时没有饮品，看看其他分类吧。',
  'menu.loading': '正在加载菜单…',
  'menu.offline': '暂时无法连接到店铺。',
  'menu.retry': '重试',
  'menu.activeOrder': '订单 {id} · {status}',
  'menu.order': '订单 {id}',
  'menu.activeHint': '点这里查看取餐码',
  'menu.language': '语言',

  'shops.title': '您要在哪里取餐？',
  'shops.none': '目前没有营业的门店。',
  'shops.error': '门店列表没有加载出来。',

  'drink.size': '杯型',
  'drink.regular': '中杯',
  'drink.large': '大杯',
  'drink.sugar': '甜度',
  'drink.ice': '冰量',
  'drink.add': '加入订单',
  'drink.save': '保存修改',
  'drink.close': '关闭',
  'drink.from': '{name}，{price} 起',
  'nutri.sugar': '含糖 {percent}%',

  'bar.review': '查看订单',
  'bar.label': '查看订单，{drinks}，{total}',

  'cart.emptyTitle': '您的订单是空的',
  'cart.emptyText': '从菜单里选一杯饮品开始吧。',
  'cart.browse': '浏览菜单',
  'cart.pickUpAt': '取餐门店：{shop}',
  'cart.designed': '自调',
  'cart.detail': '{size} · 甜度 {sugar} · 冰量 {ice}',
  'cart.edit': '修改',
  'cart.editLabel': '修改 {name}',
  'cart.remove': '删除 {name}',
  'cart.less': '{name} 减一杯',
  'cart.more': '{name} 加一杯',
  'cart.drinks': '{count} 杯饮品',
  'cart.placing': '正在下单…',
  'cart.place': '下单',
  'cart.tooMany': '每张订单最多 {max} 杯。请删掉一些，或在这张订单之后再下一单。',
  'cart.soldOut': '抱歉，以下饮品库存不足：{names}',
  'cart.busy': '您的网络目前下单较多，请稍等一分钟再试。',
  'cart.offline': '暂时无法连接到店铺。请检查网络后重试。',
  'closed.machine_offline': '这家店目前暂停营业。请稍后再试，或选择其他门店。',
  'closed.maintenance': '这家店正在维护。请稍后再试，或选择其他门店。',
  'closed.machine_not_ready': '这家店的机器需要补充原料或检查后才能制作饮品。请稍后再试，或选择其他门店。',

  'pay.orderNumber': '订单号',
  'pay.collectAt': '取餐门店：{shop}',
  'pay.cancelled': '此订单已取消，没有扣任何费用。',
  'pay.collected': '已取餐，请慢用！',
  'pay.step1': '1. 用 PayNow 付款',
  'pay.paid': '已付款',
  'pay.testMode': '测试模式：不会真实扣款',
  'pay.qrAlt': 'PayNow 付款二维码',
  'pay.ref': '参考号：{ref}',
  'pay.payBy': '请在 {time} 前付款，否则订单会被取消。',
  'pay.hint': '先截图保存这个二维码，再打开银行 App，选择“扫码付款”，从相册选这张截图。',
  'pay.received': '已收到付款 {amount}，谢谢！',
  'pay.step2': '2. 到机器取餐',
  'pay.codeLater': '付款成功后，取餐码才能使用。',
  'pay.cancel': '取消订单',
  'pay.cancelling': '正在取消…',
  'pay.newOrder': '开始新订单',
  'pay.retry': '重试',
  'pay.qrError': '付款二维码没有加载出来。',
  'status.unpaid': '等待付款',
  'status.paid': '已付款',
  'status.PREPARING': '制作中',
  'status.READY': '可以取餐',
  'progress.PREPARING': '正在为您制作饮品。',
  'progress.READY': '饮品已做好，请到机器取餐。',
  'progress.FAILED': '抱歉，机器无法制作您的饮品。已通知工作人员。',
  'progress.REFUND_NEEDED': '抱歉，您的饮品无法制作，款项正在退回。',

  'pickup.missing': '您的取餐码在下单后的页面上。',
  'pickup.qr': '二维码',
  'pickup.pin': '取餐码',
  'pickup.qrAlt': '取餐二维码',
  'pickup.qrHint': '把二维码对准机器上的扫码器。',
  'pickup.pinLabel': '取餐码 {digits}',
  'pickup.pinHint': '在机器屏幕上输入这个取餐码。',

  'designer.chooseShop': '请先选择门店。',
  'designer.loadError': '调饮页面没有加载出来，请稍后再试。',
  'designer.loading': '加载中…',
  'designer.cupSize': '杯型',
  'designer.soldOut': '售罄',
  'designer.included': '已含',
  'designer.sugarIce': '甜度和冰量',
  'designer.price': '价格',
  'designer.kioskQr': '点单机二维码',
  'designer.chooseLiquid': '请至少选一种液体',
  'designer.ownDrink': '我的自调饮品',
  'designer.per100': 'Nutri-Grade\n每 100 毫升：糖 {sugar} 克\n饱和脂肪 {fat} 克',
  'designer.scanTitle': '在点单机上扫描',
  'designer.scanText': '把二维码对准点单机的扫码器，您的饮品就会出现在屏幕上。',
  'designer.done': '完成',
};

const STRINGS: Record<Lang, Partial<Record<string, string>>> = { en, zh };

export type Translate = (key: Key | `cat.${string}` | `closed.${string}` | `status.${string}` | `progress.${string}`, vars?: Record<string, string | number>) => string;

export function translate(lang: Lang, key: string, vars: Record<string, string | number> = {}) {
  // Chinese has no singular form, so only a table that has the key itself is asked for 'key_one'
  const own = STRINGS[lang][key] !== undefined ? STRINGS[lang] : STRINGS.en;
  const text = (vars.count === 1 ? own[`${key}_one`] : undefined) ?? own[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (whole, name) => (name in vars ? String(vars[name]) : whole));
}

const STORAGE_KEY = 'drink-shop/lang';

function phoneLanguage(): Lang {
  try {
    return getLocales()[0]?.languageCode === 'zh' ? 'zh' : 'en';
  } catch {
    return 'en';
  }
}

const LanguageContext = createContext<{ lang: Lang; setLang: (lang: Lang) => void }>({ lang: 'en', setLang: () => {} });

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(phoneLanguage);

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY)
      .then((saved) => { if (saved === 'en' || saved === 'zh') setLangState(saved); })
      .catch(() => {});
  }, []);

  const value = useMemo(() => ({
    lang,
    setLang: (next: Lang) => {
      setLangState(next);
      AsyncStorage.setItem(STORAGE_KEY, next).catch(() => {});
    },
  }), [lang]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export const useLanguage = () => useContext(LanguageContext);

export function useT(): Translate {
  const { lang } = useContext(LanguageContext);
  return useCallback<Translate>((key, vars) => translate(lang, key, vars), [lang]);
}
