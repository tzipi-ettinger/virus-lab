// A source file's name, shortened in the middle when long ("צילום מסך…145900.png")
// with the full name in the tooltip. Its last word ("145900.png") is set left to
// right, so a Hebrew name doesn't show its extension first ("png.145900").
// Owner: B

import { FILE_NAME_MAX, shortFileName } from "./shortFileName";

interface FileNameProps {
  name: string;
  /** Shorten past this many characters; 0 shows the whole name. */
  max?: number;
  className?: string;
}

export function FileName({ name, max = FILE_NAME_MAX, className }: FileNameProps) {
  const { head, tail, cut } = shortFileName(name, max || Infinity);
  return (
    <bdi className={className} title={cut ? name : undefined}>
      {head}
      {cut && "…"}
      <bdi dir="ltr">{tail}</bdi>
    </bdi>
  );
}

export default FileName;
