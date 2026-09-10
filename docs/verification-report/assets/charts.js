(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // --- Chart 1: exact-match vs live comparison ---
  var chart1 = echarts.init(document.getElementById('chart-compare'), null, { renderer: 'svg' });
  chart1.setOption({
    animation: false,
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, appendToBody: true },
    legend: {
      data: ['精确匹配基线', '真实模型 (live)'],
      top: 5,
      textStyle: { color: muted, fontSize: 12 }
    },
    grid: { left: '8%', right: '5%', bottom: '10%', top: '18%' },
    xAxis: {
      type: 'category',
      data: ['判定准确率 (%)', '分数 MAE (×100)'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 12 }
    },
    yAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    series: [
      {
        name: '精确匹配基线',
        type: 'bar',
        data: [83.3, 25.0],
        itemStyle: { color: muted, borderRadius: [4, 4, 0, 0] },
        barWidth: '30%'
      },
      {
        name: '真实模型 (live)',
        type: 'bar',
        data: [90.0, 17.7],
        itemStyle: { color: accent, borderRadius: [4, 4, 0, 0] },
        barWidth: '30%'
      }
    ]
  });
  window.addEventListener('resize', function() { chart1.resize(); });

  // --- Chart 2: latency distribution ---
  var chart2 = echarts.init(document.getElementById('chart-latency'), null, { renderer: 'svg' });
  chart2.setOption({
    animation: false,
    tooltip: { trigger: 'axis', appendToBody: true, formatter: function(p) { return p[0].name + ': ' + p[0].value + ' ms'; } },
    grid: { left: '15%', right: '8%', bottom: '10%', top: '15%' },
    xAxis: {
      type: 'category',
      data: ['P50 (中位数)', 'P95 (95分位)'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 12 }
    },
    yAxis: {
      type: 'value',
      name: 'ms',
      nameTextStyle: { color: muted, fontSize: 11 },
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    series: [{
      type: 'bar',
      data: [1058, 1414],
      itemStyle: {
        color: function(params) { return params.dataIndex === 0 ? accent2 : accent; },
        borderRadius: [4, 4, 0, 0]
      },
      barWidth: '40%',
      label: {
        show: true,
        position: 'top',
        color: ink,
        fontSize: 13,
        fontWeight: 600,
        formatter: '{c} ms'
      }
    }]
  });
  window.addEventListener('resize', function() { chart2.resize(); });
})();
