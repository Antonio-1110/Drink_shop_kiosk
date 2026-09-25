import { router } from 'expo-router';

import ShopList from '@/components/ShopList';

export default function ShopsScreen() {
  return <ShopList onChosen={() => router.back()} />;
}
