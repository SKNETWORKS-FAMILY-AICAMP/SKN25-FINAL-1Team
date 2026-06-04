export const TIMELINE_HOUR_HEIGHT = 76;
export const TIMELINE_MIN_CARD_HEIGHT = 42;
export const TIMELINE_BOTTOM_PADDING = 28;
export const DEFAULT_TIMELINE_START = "09:00";
export const DEFAULT_TIMELINE_END = "18:00";
export const LUNCH_START = "12:00";
export const LUNCH_END = "13:00";

export interface TimelineTimeRange {
  start: string;
  end: string;
}

export interface TimelineRange {
  startMinutes: number;
  endMinutes: number;
}

export interface TimelineScaleOptions {
  hourHeight?: number;
  bottomPadding?: number;
}

export interface PositionedTimelineItem<T extends TimelineTimeRange> {
  item: T;
  top: number;
  height: number;
  durationMinutes: number;
  timeLabel: string;
  columnIndex: number;
  columnCount: number;
}

export function parseTimeToMinutes(time: string) {
  const [hour = "0", minute = "0"] = time.split(":");
  return Number(hour) * 60 + Number(minute);
}

export function formatMinutesAsTime(minutes: number) {
  const hour = Math.floor(minutes / 60);
  const minute = minutes % 60;

  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

export function getTimelineRange(items: TimelineTimeRange[] = []): TimelineRange {
  const defaultStart = parseTimeToMinutes(DEFAULT_TIMELINE_START);
  const defaultEnd = parseTimeToMinutes(DEFAULT_TIMELINE_END);
  const lunchStart = parseTimeToMinutes(LUNCH_START);
  const lunchEnd = parseTimeToMinutes(LUNCH_END);

  const itemStarts = items.map((item) => parseTimeToMinutes(item.start));
  const itemEnds = items.map((item) => parseTimeToMinutes(item.end));
  const minStart = Math.min(defaultStart, lunchStart, ...itemStarts);
  const maxEnd = Math.max(defaultEnd, lunchEnd, ...itemEnds);

  return {
    startMinutes: Math.floor(minStart / 60) * 60,
    endMinutes: Math.ceil(maxEnd / 60) * 60,
  };
}

export function getTimelineHeight(range: TimelineRange) {
  return getScaledTimelineHeight(range);
}

export function getScaledTimelineHeight(
  range: TimelineRange,
  options: TimelineScaleOptions = {}
) {
  const hourHeight = options.hourHeight ?? TIMELINE_HOUR_HEIGHT;
  const bottomPadding = options.bottomPadding ?? TIMELINE_BOTTOM_PADDING;

  return (
    ((range.endMinutes - range.startMinutes) / 60) * hourHeight + bottomPadding
  );
}

export function getHourTicks(
  range: TimelineRange,
  options: TimelineScaleOptions = {}
) {
  const ticks: Array<{ minutes: number; label: string; top: number }> = [];
  const hourHeight = options.hourHeight ?? TIMELINE_HOUR_HEIGHT;

  for (
    let minutes = range.startMinutes;
    minutes <= range.endMinutes;
    minutes += 60
  ) {
    ticks.push({
      minutes,
      label: formatMinutesAsTime(minutes),
      top: ((minutes - range.startMinutes) / 60) * hourHeight,
    });
  }

  return ticks;
}

export function getTimelineBlockMetrics(
  start: string,
  end: string,
  range: TimelineRange,
  options: TimelineScaleOptions = {}
) {
  const startMinutes = parseTimeToMinutes(start);
  const endMinutes = Math.max(parseTimeToMinutes(end), startMinutes + 5);
  const durationMinutes = endMinutes - startMinutes;
  const hourHeight = options.hourHeight ?? TIMELINE_HOUR_HEIGHT;

  return {
    top: ((startMinutes - range.startMinutes) / 60) * hourHeight,
    height: (durationMinutes / 60) * hourHeight,
    durationMinutes,
    timeLabel: `${formatMinutesAsTime(startMinutes)} ~ ${formatMinutesAsTime(endMinutes)}`,
  };
}

export function getLunchBlockMetrics(
  range: TimelineRange,
  options: TimelineScaleOptions = {}
) {
  return getTimelineBlockMetrics(LUNCH_START, LUNCH_END, range, options);
}

export function buildPositionedTimelineItems<T extends TimelineTimeRange>(
  items: T[],
  range: TimelineRange,
  options: TimelineScaleOptions = {}
): PositionedTimelineItem<T>[] {
  const sortedItems = [...items].sort((left, right) => {
    const startDiff =
      parseTimeToMinutes(left.start) - parseTimeToMinutes(right.start);

    if (startDiff !== 0) {
      return startDiff;
    }

    return parseTimeToMinutes(left.end) - parseTimeToMinutes(right.end);
  });

  const groups: T[][] = [];
  let currentGroup: T[] = [];
  let currentGroupEnd = -1;

  for (const item of sortedItems) {
    const startMinutes = parseTimeToMinutes(item.start);
    const endMinutes = parseTimeToMinutes(item.end);

    if (!currentGroup.length || startMinutes < currentGroupEnd) {
      currentGroup.push(item);
      currentGroupEnd = Math.max(currentGroupEnd, endMinutes);
      continue;
    }

    groups.push(currentGroup);
    currentGroup = [item];
    currentGroupEnd = endMinutes;
  }

  if (currentGroup.length) {
    groups.push(currentGroup);
  }

  return groups.flatMap((group) => {
    const activeColumns: number[] = [];
    const columnByItem = new Map<T, number>();
    let columnCount = 1;

    for (const item of group) {
      const startMinutes = parseTimeToMinutes(item.start);
      const endMinutes = parseTimeToMinutes(item.end);
      let columnIndex = activeColumns.findIndex(
        (activeEnd) => activeEnd <= startMinutes
      );

      if (columnIndex === -1) {
        columnIndex = activeColumns.length;
        activeColumns.push(endMinutes);
      } else {
        activeColumns[columnIndex] = endMinutes;
      }

      columnByItem.set(item, columnIndex);
      columnCount = Math.max(columnCount, activeColumns.length);
    }

    return group.map((item) => ({
      item,
      ...getTimelineBlockMetrics(item.start, item.end, range, options),
      columnIndex: columnByItem.get(item) ?? 0,
      columnCount,
    }));
  });
}
