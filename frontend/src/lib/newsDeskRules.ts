export const newsWordCount = (text: string) => text.trim() ? text.trim().split(/\s+/).length : 0;
export const articleWordsValid = (text: string) => newsWordCount(text) >= 200 && newsWordCount(text) <= 300;
export const scriptWordsValid = (text: string) => newsWordCount(text) >= 60 && newsWordCount(text) <= 95;
