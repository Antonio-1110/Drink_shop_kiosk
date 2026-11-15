import React from 'react';
import { GRADE_COLORS } from '../nutrigrade';
import { useT } from '../i18n';
import './NutriGradeMark.css';

// HPB Nutri-Grade mark: the grade and the sugar per 100 mL. Menus must show it next to every C or D
// drink (the backend's `label_required`); A and B are optional, so they stay off to keep the menu calm.
// `grade` is the drink's nutri_grade from GET /ordering/drinks/ (null when it has no recipe yet).
function NutriGradeMark({ grade, size = 'sm' }) {
    const t = useT();
    if (!grade?.label_required) return null;
    const sugar = t('nutri.sugar', { percent: grade.sugar_percent });
    return (
        <span className={`nutri-mark nutri-mark-${size}`} role="img" aria-label={`Nutri-Grade ${grade.grade}, ${sugar}`}>
            <span className="nutri-mark-letter" style={{ background: GRADE_COLORS[grade.grade] }}>{grade.grade}</span>
            <span className="nutri-mark-text">
                <span>Nutri-Grade</span>
                <strong>{sugar}</strong>
            </span>
        </span>
    );
}

export default NutriGradeMark;
