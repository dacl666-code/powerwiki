// 通用交互脚本

// 移动端菜单切换（如需扩展）
document.addEventListener('DOMContentLoaded', function() {
    // 自动隐藏 flash 消息
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            alert.style.opacity = '0';
            alert.style.transition = 'opacity 0.5s';
            setTimeout(function() {
                alert.remove();
            }, 500);
        }, 3000);
    });

    // 首字母自动填充
    const nameInput = document.getElementById('name');
    const firstLetterInput = document.getElementById('first_letter');
    if (nameInput && firstLetterInput && !firstLetterInput.value) {
        nameInput.addEventListener('blur', function() {
            if (nameInput.value && !firstLetterInput.value) {
                const first = nameInput.value.trim().charAt(0).toUpperCase();
                firstLetterInput.value = first;
            }
        });
    }
});
