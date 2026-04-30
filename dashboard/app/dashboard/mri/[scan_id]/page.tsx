export const dynamic = "force-dynamic";

import { MriCommandCenter } from "./MriCommandCenter";
import { getMockMri } from "./mri-mock-data";

interface PageProps {
  params: Promise<{ scan_id: string }>;
}

export default async function MriCommandCenterPage({ params }: PageProps) {
  const { scan_id } = await params;
  const data = getMockMri(scan_id);
  return <MriCommandCenter data={data} />;
}
