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


================================================================
  【文件列表结束】

  完整目录结构：
  powerwiki/
  ├── app.py                  主程序
  ├── export_static.py        静态导出【新增】
  ├── deploy.bat              Pages部署【新增】
  ├── requirements.txt
  ├── README.md
  ├── data/                   (首次运行自动生成)
  ├── dist/                   (导出后生成)
  ├── static/
  │   ├── css/style.css
  │   ├── js/main.js
  │   └── uploads/            (首次运行自动生成)
  └── templates/
      ├── base.html
      ├── index.html
      ├── category.html
      ├── character_detail.html
      ├── realm_detail.html
      ├── wiki_page.html
      ├── search.html
      ├── login.html
      └── admin/
          ├── dashboard.html
          ├── characters.html
          ├── character_edit.html
          ├── categories.html
          ├── category_edit.html
          ├── realms.html
          ├── realm_edit.html
          ├── pages.html
          └── page_edit.html
================================================================
