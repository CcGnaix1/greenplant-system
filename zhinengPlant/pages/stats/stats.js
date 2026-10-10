// pages/stats/stats.js
const api = require('../../utils/request')
const weeks = ['3周前','2周前','上周','本周']
const water = [2, 3, 2, 4]
const months = ['4月','5月','6月','7月','8月','9月']
const heights = [40, 48, 56, 66, 76, 86]
const maxH = Math.max.apply(null, heights)

Page({
  data: { weeks: [], water: [], bars: [], waterTotal: 0, avgWater: 0 },
  onLoad(opt) { this.plantId = opt.id || 1 },
  onShow() {
    api.call('/plant/stats', { data: { id: this.plantId } }).then(res => {
      const d = res.data || {}
      const growth = d.growth || []
      const hs = growth.map(x => Number(x.heightCm) || 0)
      const max = Math.max.apply(null, hs.concat([1]))
      this.setData({
        weeks: ['累计'],
        water: [d.waterCount || 0],
        bars: growth.map(x => ({ m: String(x.date || '').slice(5, 10), h: Number(x.heightCm) || 0, pct: Math.round((Number(x.heightCm) || 0) / max * 100) })),
        waterTotal: d.waterCount || 0,
        avgWater: d.waterCount || 0
      })
    }).catch(() => wx.showToast({ title: '统计加载失败', icon: 'none' }))
  }
})
