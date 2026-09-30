// Preview of the HPB Nutri-Grade, using the same per-100 mL limits as the backend's
// operation/health_metrics.py. The backend's grade is the one recorded on the order.
const SUGAR_LIMITS = [['A', 1], ['B', 5], ['C', 10]];
const SAT_FAT_LIMITS = [['A', 0.7], ['B', 1.2], ['C', 2.8]];
const ORDER = ['A', 'B', 'C', 'D'];

const gradeFor = (value, limits) => (limits.find(([, max]) => value <= max) ?? ['D'])[0];

// the final grade is the worse of sugar and saturated fat; any sweetener rules out A
export function nutriGrade(sugarPer100, satFatPer100, hasSweetener = false) {
    let grade = ORDER[Math.max(
        ORDER.indexOf(gradeFor(sugarPer100, SUGAR_LIMITS)),
        ORDER.indexOf(gradeFor(satFatPer100, SAT_FAT_LIMITS)),
    )];
    if (hasSweetener && grade === 'A') grade = 'B';
    return grade;
}

// HPB's label colours
export const GRADE_COLORS = { A: '#00843d', B: '#7ab800', C: '#f5a300', D: '#e03c31' };
