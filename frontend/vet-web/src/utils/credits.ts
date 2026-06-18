import { poster } from "./credits-poster";

/**
 * 개발자도구 콘솔 이스터에그.
 * 콘솔을 여는 사람에게만 팀 포스터(Angel of Jazz)와 크레딧을 보여준다.
 * 포스터는 data URI라 콘솔(devtools origin)에서도 origin/네트워크 무관하게 렌더된다.
 */
export function printCredits() {
  if (typeof window === "undefined") return;

  const w = 260;
  const h = 260;
  console.log(
    "%c ",
    [
      "font-size: 0",
      `line-height: ${h}px`,
      `padding: ${h / 2}px ${w / 2}px`,
      // shorthand(`/` 포함)는 콘솔 %c 파서가 거부하므로 속성을 풀어서 지정한다.
      `background-image: url("${poster}")`,
      "background-repeat: no-repeat",
      "background-position: center",
      `background-size: ${w}px ${h}px`,
    ].join(";")
  );
  console.log(
    "%cpaw o paw%c  —  5 members, one harmony.",
    "color:#a01b3f;font-weight:800;font-size:15px",
    "color:#c89b2c;font-weight:600;font-size:12px"
  );
  console.log("%cTeam MEDIPAW · Angel of Jazz 🎷", "color:#888;font-size:11px");
}
