<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, AriaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, AriaComponent, CanvasRenderer])
const props = defineProps({ option: { type: Object, required: true }, label: { type: String, required: true } })
const element = ref(null)
let chart, observer
function render() {
  chart?.setOption({ animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches, ...props.option,
    aria: { enabled: true, description: props.label }, tooltip: { renderMode: 'richText', ...props.option.tooltip } }, true)
}
onMounted(() => {
  chart = echarts.init(element.value)
  render()
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(element.value)
})
watch(() => props.option, render, { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose(); chart = null })
</script>
<template><div ref="element" class="chart" role="img" :aria-label="label"></div></template>
