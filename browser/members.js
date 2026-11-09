// MEMBERSHIP — run on https://en.wikipedia.org/wiki/List_of_S%26P_500_companies
// Returns "SYMBOL|Name;SYMBOL|Name;..." in Yahoo format (BRK.B -> BRK-B). Alphabet is kept once, as GOOG.
// Save the result as members.txt.
[...document.querySelectorAll('#constituents tbody tr')]
  .map((tr) => tr.querySelectorAll('td'))
  .filter((td) => td.length > 1)
  .map((td) => td[0].textContent.trim().replace(/\./g, '-') + '|' + td[1].textContent.trim())
  .filter((x) => !x.startsWith('GOOGL|'))
  .join(';')
