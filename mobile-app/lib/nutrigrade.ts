// Preview of the HPB Nutri-Grade, using the same per-100 mL limits as the backend's
// operation/health_metrics.py. The backend's grade is the one recorded on the order.
const SUGAR_LIMITS: [Grade, number][] = [['A', 1], ['B', 5], ['C', 10]];
const SAT_FAT_LIMITS: [Grade, number][] = [['A', 0.7], ['B', 1.2], ['C', 2.8]];
export type Grade = 'A' | 'B' | 'C' | 'D';
const ORDER: Grade[] = ['A', 'B', 'C', 'D'];

const gradeFor = (value: number, limits: [Grade, number][]): Grade => limits.find(([, max]) => value <= max)?.[0] ?? 'D';

// the final grade is the worse of sugar and saturated fat; any sweetener rules out A
export function nutriGrade(sugarPer100: number, satFatPer100: number, hasSweetener = false): Grade {
  let grade = ORDER[Math.max(
    ORDER.indexOf(gradeFor(sugarPer100, SUGAR_LIMITS)),
    ORDER.indexOf(gradeFor(satFatPer100, SAT_FAT_LIMITS)),
  )];
  if (hasSweetener && grade === 'A') grade = 'B';
  return grade;
}

// HPB's label colours
export const GRADE_COLORS: Record<Grade, string> = { A: '#00843d', B: '#7ab800', C: '#f5a300', D: '#e03c31' };
