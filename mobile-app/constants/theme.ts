// "Matcha & milk tea": deep tea green for actions, cream and latte tones for surfaces,
// brown-sugar amber for prices and highlights.
export const colors = {
  primary: '#0f5c4d', // tea green: buttons, selected chips, headings
  primarySoft: '#dcefe7', // unselected chips, info panels
  accent: '#b86e1f', // brown sugar: prices
  header: '#f3ebe0', // latte: headers and tab bar
  cream: '#f6efe4', // card footers
  secondary: '#e6dccd', // secondary buttons
  background: '#fbf7f1', // milk
  surface: '#ffffff',
  text: '#2b2320', // dark roast
  muted: '#7a6e66',
  border: '#e9e0d3',
  errorBg: '#fde4e1',
  errorText: '#9b2c1f',
};

// Fraunces (serif) for names and headings, Inter for everything else, matching the kiosk.
// Loaded in app/_layout.tsx; until they load, the system fonts are used.
export const fonts = {
  serif: 'Fraunces_500Medium',
  serifBold: 'Fraunces_600SemiBold',
  sans: 'Inter_400Regular',
  sansMedium: 'Inter_500Medium',
  sansBold: 'Inter_600SemiBold',
};
