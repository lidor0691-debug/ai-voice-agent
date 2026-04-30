export const dynamic = "force-dynamic";

import { MayaHome } from "./MayaHome";
import { getMockHome } from "./maya-home-mock";

export default async function MayaHomePage() {
  const data = getMockHome();
  return <MayaHome data={data} />;
}
