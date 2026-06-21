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

// 顏色名 → 16 進位（給 BC required_colors 徽章用）
const COLOR_HEX = {
  Red: '#FF4444', Grn: '#44BB44', Blu: '#4488FF',
  Yel: '#FFCC00', Pur: '#AA44CC', Brn: '#886644',
  Blue: '#4488FF', Green: '#44BB44', Yellow: '#FFCC00',
  Purple: '#AA44CC', Orange: '#FF8800',
};

// 全域 asset 版本號（由 Python 端在「套用新美術」後遞增,用來打破瀏覽器快取）
let ASSET_VERSION = 0;

function imgUrl(key) {
  // 相對路徑會解析成 iframe 相對於 index.html 的位置
  const base = `assets/${encodeURIComponent(key)}.png`;
  return ASSET_VERSION ? `${base}?v=${ASSET_VERSION}` : base;
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

  // void = 盤面外的格,透明（保持 .grid 黑色底完整,不挖洞）
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
    if (!cell.middle.covered) {
      const layer = makeLayer(cell.middle, 'middle');
      const span = cell.middle.span || 1;
      if (span > 1) {
        // 大圖跨 span x span 格（cells 之間無 gap）
        layer.style.width = (span * args.cell_size) + 'px';
        layer.style.height = (span * args.cell_size) + 'px';
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
    // 飲料櫃 per-cell 瓶色 — 不論 anchor / covered 都要在「自己的格」上畫
    if (cell.middle.bottle_color) {
      const bottle = document.createElement('div');
      bottle.className = 'bottle';
      if (cell.middle.bottle_alive) {
        bottle.style.background = COLOR_HEX[cell.middle.bottle_color] || '#888';
      } else {
        bottle.classList.add('dead');
      }
      div.appendChild(bottle);
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
  if (typeof args.asset_version === 'number') {
    ASSET_VERSION = args.asset_version;
  }
  const root = document.getElementById('root');
  root.innerHTML = '';

  const wrap = document.createElement('div');
  wrap.className = 'wrap';

  const board = document.createElement('div');
  board.className = 'board';

  // 內層格子區（黑色,明顯區隔可遊玩區域）
  const grid = document.createElement('div');
  grid.className = 'grid';
  for (let r = 0; r < args.board.length; r++) {
    const row = document.createElement('div');
    row.className = 'row';
    for (let c = 0; c < args.board[r].length; c++) {
      row.appendChild(renderCell(args.board[r][c], r, c, args));
    }
    grid.appendChild(row);
  }
  board.appendChild(grid);
  wrap.appendChild(board);
  root.appendChild(wrap);

  // 設定 iframe 高度（cells 無間距;只算 board 18px padding + 上下緩衝）
  const rows = args.board.length;
  const totalHeight = rows * args.cell_size + 60;
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
