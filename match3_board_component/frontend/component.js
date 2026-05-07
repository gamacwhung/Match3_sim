/**
 * Match3 Board Custom Streamlit Component (vanilla JS)
 *
 * 接受 args:
 *   board:           二維 cell 陣列；每格 {middle, upper, bottom, locked, mud}
 *                    每個 layer = {id, hp, image_key, css_color?, css_label?}
 *   selected:        [r, c] | null
 *   mode:            'play' | 'preview'
 *   cell_size:       int (px)
 *
 * 點擊時回傳:
 *   { type: 'click', r, c, ts }
 */

// ===== Streamlit 通訊（最小實作，不依賴 streamlit-component-lib npm 套件） =====
const Streamlit = {
  setComponentReady() {
    window.parent.postMessage(
      { isStreamlitMessage: true, type: 'streamlit:componentReady', apiVersion: 1 },
      '*'
    );
  },
  setFrameHeight(height) {
    window.parent.postMessage(
      { isStreamlitMessage: true, type: 'streamlit:setFrameHeight', height },
      '*'
    );
  },
  setComponentValue(value) {
    window.parent.postMessage(
      {
        isStreamlitMessage: true,
        type: 'streamlit:setComponentValue',
        value,
        dataType: 'json',
      },
      '*'
    );
  },
};

// ===== 渲染 =====
const POWERUP_IDS = new Set(['Soda0d', 'Soda90', 'TNT', 'TrPr', 'LtBl']);

function imgUrl(key) {
  // 相對路徑會解析成 iframe 相對於 index.html 的位置
  return `assets/${encodeURIComponent(key)}.png`;
}

function makeLayer(layerData, layerName) {
  // 優先用圖片；若沒有 image_key 則 CSS fallback
  if (layerData.image_key) {
    const img = document.createElement('img');
    img.className = `layer ${layerName}`;
    img.src = imgUrl(layerData.image_key);
    img.alt = layerData.id || '';
    img.draggable = false;
    // 圖片載入失敗 → 改用 fallback
    img.onerror = () => {
      img.replaceWith(makeFallback(layerData));
    };
    return img;
  }
  return makeFallback(layerData);
}

function makeFallback(layerData) {
  const div = document.createElement('div');
  div.className = 'fallback';
  if (layerData.is_obstacle) div.classList.add('obstacle');
  div.style.background = layerData.css_color || '#666';
  div.textContent = layerData.css_label || (layerData.id || '').slice(0, 4);
  return div;
}

function renderCell(cell, r, c, args) {
  const div = document.createElement('div');
  div.className = 'cell';
  div.style.width = `${args.cell_size}px`;
  div.style.height = `${args.cell_size}px`;

  // void = 不存在的格 → 透明,不可點
  if (cell.void) {
    div.classList.add('void');
    return div;
  }

  const isSelected =
    args.selected && args.selected[0] === r && args.selected[1] === c;
  if (isSelected) div.classList.add('selected');

  if (!cell.middle) div.classList.add('empty');

  if (cell.middle && POWERUP_IDS.has(cell.middle.id)) {
    div.classList.add('powerup');
  }

  // bottom 層
  if (cell.bottom) {
    div.appendChild(makeLayer(cell.bottom, 'bottom'));
    if (cell.bottom.hp && cell.bottom.hp > 1) {
      const hp = document.createElement('div');
      hp.className = 'hp bottom';
      hp.textContent = cell.bottom.hp;
      div.appendChild(hp);
    }
  }

  // middle 層
  if (cell.middle) {
    if (cell.middle.covered) {
      // 被左上角 anchor 的大圖蓋住,不畫
    } else {
      const layer = makeLayer(cell.middle, 'middle');
      const span = cell.middle.span || 1;
      if (span > 1) {
        // 大圖跨 span x span 格;cell_size 加上每格之間的 2px gap
        const sizePx = span * args.cell_size + (span - 1) * 2;
        layer.style.width = sizePx + 'px';
        layer.style.height = sizePx + 'px';
        layer.classList.add('span');
      }
      div.appendChild(layer);
      if (cell.middle.hp && cell.middle.hp > 1) {
        const hp = document.createElement('div');
        hp.className = 'hp middle';
        hp.textContent = cell.middle.hp;
        div.appendChild(hp);
      }
    }
  }

  // mud 罩在中層上面（額外暗化）
  if (cell.mud) {
    const mud = document.createElement('div');
    mud.className = 'mud-overlay';
    div.appendChild(mud);
  }

  // upper 層
  if (cell.upper) {
    div.appendChild(makeLayer(cell.upper, 'upper'));
    if (cell.upper.hp && cell.upper.hp > 1) {
      const hp = document.createElement('div');
      hp.className = 'hp upper';
      hp.textContent = cell.upper.hp;
      div.appendChild(hp);
    }
  }

  if (args.mode === 'play') {
    div.classList.add('clickable');
    div.addEventListener('click', () => {
      Streamlit.setComponentValue({
        type: 'click',
        r,
        c,
        ts: Date.now(),
      });
    });
  }

  return div;
}

function render(args) {
  const root = document.getElementById('root');
  root.innerHTML = '';

  const wrap = document.createElement('div');
  wrap.className = 'wrap';

  const board = document.createElement('div');
  board.className = 'board';
  if (args.mode === 'preview') {
    board.classList.add('preview');
  }

  for (let r = 0; r < args.board.length; r++) {
    const row = document.createElement('div');
    row.className = 'row';
    for (let c = 0; c < args.board[r].length; c++) {
      row.appendChild(renderCell(args.board[r][c], r, c, args));
    }
    board.appendChild(row);
  }
  wrap.appendChild(board);
  root.appendChild(wrap);

  // 設定 iframe 高度
  const rows = args.board.length;
  const totalHeight = rows * (args.cell_size + 2) + 32;
  Streamlit.setFrameHeight(totalHeight);
}

// ===== 訊息接收 =====
window.addEventListener('message', (event) => {
  if (!event.data || !event.data.type) return;
  if (event.data.type === 'streamlit:render') {
    render(event.data.args);
  }
});

Streamlit.setComponentReady();
// 初始給個高度（避免 streamlit 把 iframe 收成 0）
Streamlit.setFrameHeight(100);
