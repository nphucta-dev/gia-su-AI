export const topics = [
  { id: 'quadratic', name: 'Phương trình bậc hai', chapter: 'Chương 1 · Đại số', progress: 72, description: 'Biệt thức, nghiệm và hệ thức Viète.' },
  { id: 'functions', name: 'Hàm số và đồ thị', chapter: 'Chương 1 · Đại số', progress: 40, description: 'Khảo sát hàm số và đọc đồ thị.' },
  { id: 'inequality', name: 'Bất đẳng thức', chapter: 'Chương 1 · Đại số', progress: 20, description: 'Biến đổi và chứng minh bất đẳng thức.' }
];
export const questions = [
 { text: 'Nghiệm của phương trình x² − 5x + 6 = 0 là?', options: ['1 và 6', '2 và 3', '−2 và −3', 'Không có nghiệm'], correct: 1, explanation: 'x² − 5x + 6 = (x − 2)(x − 3). Vậy x = 2 hoặc x = 3.' },
 { text: 'Biệt thức Δ của ax² + bx + c = 0 được tính bằng?', options: ['b² − 4ac', 'a² − 4bc', 'b² + 4ac', '2b − 4ac'], correct: 0, explanation: 'Biệt thức Δ = b² − 4ac, với a khác 0.' },
 { text: 'Khi Δ < 0, phương trình bậc hai có bao nhiêu nghiệm thực?', options: ['Hai nghiệm', 'Một nghiệm kép', 'Không có nghiệm thực', 'Vô số nghiệm'], correct: 2, explanation: 'Δ âm nên căn bậc hai của Δ không thuộc tập số thực.' },
 { text: 'Tổng hai nghiệm của ax² + bx + c = 0 bằng?', options: ['c/a', '−b/a', 'b/a', '−c/a'], correct: 1, explanation: 'Theo hệ thức Viète, tổng hai nghiệm x₁ + x₂ = −b/a.' },
 { text: 'Phương trình x² − 4 = 0 có nghiệm nào?', options: ['0 và 4', 'Chỉ 2', 'Chỉ −2', '−2 và 2'], correct: 3, explanation: 'x² = 4 nên x = −2 hoặc x = 2.' }
];
