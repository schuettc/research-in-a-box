import type { SpatialCoverage } from "./generated/manifest";

const W = 360;
const H = 180;

/** Longitude and latitude to the outline's x and y (equirectangular, north up). */
const x = (lon: number) => lon + 180;
const y = (lat: number) => 90 - lat;

/**
 * Spatial coverage: the description first, then the bounding box drawn on a plain outline of
 * the world with its graticule (a box too small to see is ringed), then the numbers.
 */
export function Coverage({ coverage }: { coverage: SpatialCoverage }) {
  const [west, south, east, north] = coverage.bbox as [number, number, number, number];
  const left = x(west);
  const top = y(north);
  const width = Math.max(x(east) - left, 0);
  const height = Math.max(y(south) - top, 0);
  const small = width < 4 && height < 4;
  const lines = [];
  for (let lon = -150; lon < 180; lon += 30) {
    lines.push(<line key={`lon${lon}`} x1={x(lon)} x2={x(lon)} y1={0} y2={H} />);
  }
  for (let lat = -60; lat < 90; lat += 30) {
    lines.push(<line key={`lat${lat}`} x1={0} x2={W} y1={y(lat)} y2={y(lat)} />);
  }
  const numbers = `West ${west}, south ${south}, east ${east}, north ${north}`;
  return (
    <div className="coverage">
      {coverage.description && <p>{coverage.description}</p>}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`The area the data covers, on a world outline: ${numbers}`}
      >
        <rect className="frame" x={0} y={0} width={W} height={H} />
        <g className="graticule">{lines}</g>
        <rect className="area" x={left} y={top} width={width || 0.5} height={height || 0.5} />
        {small && <circle className="ring" cx={left + width / 2} cy={top + height / 2} r={6} />}
      </svg>
      <p className="small muted">{numbers}</p>
    </div>
  );
}
